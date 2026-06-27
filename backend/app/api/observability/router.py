import time
from fastapi import APIRouter, Query, Depends
from typing import List, Optional
from app.core.cache import trace_store
from app.api.auth.dependencies import get_current_user
from app.core.types.users import User

router = APIRouter(prefix="/api/observability")

@router.get("/traces")
async def get_traces(
    minutes: int = Query(default=30),
    workflow_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Fetch recent traces and calculate summary metrics for the dashboard, scoped by tenant/user and workflow."""
    start_time = time.time() - (minutes * 60)
    
    # Enforce role-based isolation scope
    customer_id = None
    user_id = None
    
    if current_user.role == "system_admin":
        pass  # Global visibility
    elif current_user.role == "admin":
        customer_id = current_user.customer_id  # Tenant visibility
    else:
        user_id = current_user.id  # Owner/Creator visibility
        
    traces = await trace_store.get_traces_in_range(
        start_time=start_time,
        customer_id=customer_id,
        user_id=user_id,
        workflow_id=workflow_id
    )
    
    total_requests = len(traces)
    if total_requests > 0:
        avg_latency = sum(t.get("latency_ms", 0) for t in traces) / total_requests
        error_count = sum(1 for t in traces if t.get("violations") or "error" in t.get("status", ""))
    else:
        avg_latency = 0
        error_count = 0

    # Group traces by workflow_id for a chart
    workflow_distribution = {}
    for t in traces:
        wid = t.get("workflow_id") or t.get("workflow_name") or "unknown"
        workflow_distribution[wid] = workflow_distribution.get(wid, 0) + 1

    return {
        "summary": {
            "total_requests": total_requests,
            "avg_latency_ms": round(avg_latency, 2),
            "error_rate": round((error_count / total_requests * 100), 2) if total_requests > 0 else 0,
            "time_range_min": minutes
        },
        "traces": traces,
        "workflow_distribution": [{"name": k, "value": v} for k, v in workflow_distribution.items()]
    }