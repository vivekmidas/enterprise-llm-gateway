import time
from fastapi import APIRouter, Query
from typing import List, Optional
from app.core.cache import redis_cache

router = APIRouter(prefix="/api/observability")

@router.get("/traces")
async def get_traces(minutes: int = Query(default=30)):
    """Fetch recent traces and calculate summary metrics for the dashboard."""
    start_time = time.time() - (minutes * 60)
    traces = await redis_cache.get_traces_in_range(start_time)
    
    total_requests = len(traces)
    if total_requests > 0:
        avg_latency = sum(t.get("latency_ms", 0) for t in traces) / total_requests
        error_count = sum(1 for t in traces if t.get("violations") or "error" in t.get("status", ""))
    else:
        avg_latency = 0
        error_count = 0

    # Group traces by workflow_id for a chart (optional enhancement)
    workflow_distribution = {}
    for t in traces:
        wid = t.get("workflow_id", "unknown")
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