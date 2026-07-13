import time
import json
from fastapi import APIRouter, Query, Depends
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.db_models import KnowledgeBaseDB, KnowledgeDocumentDB, KnowledgeChunkDB
from app.core.cache import trace_store
from app.api.auth.dependencies import get_current_user
from app.core.types.users import User

router = APIRouter(prefix="/api/observability")

@router.get("/traces")
async def get_traces(
    minutes: int = Query(default=30),
    workflow_id: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Fetch recent traces and calculate summary metrics for the dashboard, scoped by tenant/user and workflow."""
    start_time = time.time() - (minutes * 60)
    
    # Enforce role-based isolation scope
    target_customer_id = None
    user_id = None
    
    if current_user.role == "system_admin":
        target_customer_id = customer_id  # Allow system admins to filter by customer_id if provided
    elif current_user.role == "admin":
        target_customer_id = current_user.customer_id  # Tenant visibility
    else:
        user_id = current_user.id  # Owner/Creator visibility
        
    traces = await trace_store.get_traces_in_range(
        start_time=start_time,
        customer_id=target_customer_id,
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

@router.get("/traces/{trace_id}")
async def get_trace_details(
    trace_id: str,
    current_user: User = Depends(get_current_user)
):
    """Retrieve full detail for a single trace log, scoped by permissions."""
    trace_data = await trace_store.client.get(f"trace:{trace_id}")
    if not trace_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trace execution not found")
        
    trace_dict = json.loads(trace_data)
    
    # Enforce role-based isolation scope
    if current_user.role != "system_admin":
        if current_user.role == "admin" and trace_dict.get("customer_id") != current_user.customer_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Forbidden: You cannot access execution logs of other tenants")
        elif current_user.role not in ["system_admin", "admin"] and trace_dict.get("user_id") != current_user.id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Forbidden: You cannot access other users' execution logs")
            
    return trace_dict

@router.post("/traces/{trace_id}/stop")
async def stop_trace(
    trace_id: str,
    current_user: User = Depends(get_current_user)
):
    """Stop/cancel a running workflow execution task."""
    from app.workflows.executor import WorkflowExecutor
    from fastapi import HTTPException
    
    # 1. Fetch trace to verify permissions
    trace_data = await trace_store.client.get(f"trace:{trace_id}")
    if not trace_data:
        raise HTTPException(status_code=404, detail="Trace execution not found")
        
    trace_dict = json.loads(trace_data)
    
    # Enforce role-based isolation scope
    if current_user.role != "system_admin":
        if current_user.role == "admin" and trace_dict.get("customer_id") != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot stop executions of other tenants")
        elif current_user.role not in ["system_admin", "admin"] and trace_dict.get("user_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot stop other users' executions")
            
    # 2. Check if trace task is active in registry
    task = WorkflowExecutor.active_tasks.get(trace_id)
    if not task:
        raise HTTPException(status_code=400, detail="Trace is not currently running or has already finished")
        
    # 3. Cancel task
    task.cancel()
    return {"message": f"Stop signal sent to execution trace {trace_id}"}

@router.post("/traces/{trace_id}/restart")
async def restart_trace(
    trace_id: str,
    current_user: User = Depends(get_current_user)
):
    """Restart a workflow execution using the original inputs."""
    import uuid
    from fastapi import HTTPException
    from app.workflows.executor import execute_dynamic_agent
    from app.workflows.service import get_workflow
    
    # 1. Fetch trace to retrieve inputs & configs
    trace_data = await trace_store.client.get(f"trace:{trace_id}")
    if not trace_data:
        raise HTTPException(status_code=404, detail="Trace execution not found")
        
    trace_dict = json.loads(trace_data)
    
    # Enforce role-based isolation scope
    if current_user.role != "system_admin":
        if current_user.role == "admin" and trace_dict.get("customer_id") != current_user.customer_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot restart executions of other tenants")
        elif current_user.role not in ["system_admin", "admin"] and trace_dict.get("user_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot restart other users' executions")
            
    # 2. Extract inputs, workflow_id
    workflow_id = trace_dict.get("workflow_id")
    input_content = trace_dict.get("input")
    context = trace_dict.get("context", {})
    
    if not workflow_id:
        raise HTTPException(status_code=400, detail="Cannot restart trace: missing workflow_id in trace details")
        
    # 3. Load active workflow definition from store to get latest configs
    try:
        workflow_def = await get_workflow(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Target workflow not found: {str(e)}")
        
    # 4. Generate new trace_id for restarted execution
    new_trace_id = f"tr_{uuid.uuid4().hex[:16]}"
    
    # Add restart lineage metadata
    if "metadata" not in context:
        context["metadata"] = {}
    context["metadata"]["restarted_from_trace_id"] = trace_id
    
    # 5. Execute dynamic agent in background
    import asyncio
    asyncio.create_task(
        execute_dynamic_agent(
            agent_config=workflow_def.model_dump(),
            input_content=input_content,
            trace_id=new_trace_id,
            context=context
        )
    )
    
    return {
        "message": f"Execution trace {trace_id} successfully restarted.",
        "new_trace_id": new_trace_id
    }


@router.get("/knowledge-metrics")
async def get_knowledge_metrics(
    customer_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch counts and metadata statistics of knowledge bases, documents, chunks, and storage size."""
    # Enforce role-based isolation scope
    target_customer_id = None
    if current_user.role == "system_admin":
        target_customer_id = customer_id  # System admin can filter or view aggregate
    else:
        target_customer_id = current_user.customer_id # Admins & users are restricted to their tenant
        
    from sqlalchemy import select, func
    
    # 1. Active Knowledge Bases count
    kb_query = select(func.count(KnowledgeBaseDB.id)).where(KnowledgeBaseDB.status == "active")
    if target_customer_id is not None:
        kb_query = kb_query.where(KnowledgeBaseDB.customer_id == target_customer_id)
    kb_res = await db.execute(kb_query)
    total_kbs = kb_res.scalar() or 0
    
    # 2. Documents count grouped by status
    doc_query = select(KnowledgeDocumentDB.status, func.count(KnowledgeDocumentDB.id))
    if target_customer_id is not None:
        doc_query = doc_query.where(KnowledgeDocumentDB.customer_id == target_customer_id)
    doc_query = doc_query.group_by(KnowledgeDocumentDB.status)
    doc_res = await db.execute(doc_query)
    
    doc_stats = {"completed": 0, "pending": 0, "failed": 0, "archived": 0}
    total_docs = 0
    for status_str, count in doc_res.all():
        if status_str in doc_stats:
            doc_stats[status_str] = count
        total_docs += count
        
    # 3. Total chunks/vectors count
    chunk_query = select(func.count(KnowledgeChunkDB.id))
    if target_customer_id is not None:
        chunk_query = chunk_query.where(KnowledgeChunkDB.customer_id == target_customer_id)
    chunk_res = await db.execute(chunk_query)
    total_chunks = chunk_res.scalar() or 0
    
    # 4. Total storage size (sum of file_size)
    storage_query = select(func.sum(KnowledgeDocumentDB.file_size))
    if target_customer_id is not None:
        storage_query = storage_query.where(KnowledgeDocumentDB.customer_id == target_customer_id)
    storage_query = storage_query.where(KnowledgeDocumentDB.status != "archived")
    storage_res = await db.execute(storage_query)
    total_bytes = storage_res.scalar() or 0
    
    return {
        "total_kbs": total_kbs,
        "total_docs": total_docs,
        "documents_by_status": doc_stats,
        "total_chunks": total_chunks,
        "total_bytes": int(total_bytes)
    }