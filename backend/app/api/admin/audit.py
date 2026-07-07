from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import get_current_admin
from app.core.database import get_db
from app.core.types.users import User
from app.models.db_models import AuditLogDB

router = APIRouter(prefix="/admin/audit-logs", tags=["Admin"])


def _actor_id(current_user: User) -> Optional[int]:
    try:
        return int(current_user.id)
    except (TypeError, ValueError):
        return None


async def record_audit_log(
    db: AsyncSession,
    *,
    current_user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    customer_id: Optional[int] = None,
    status: str = "success",
    details: Optional[Dict[str, Any]] = None,
) -> AuditLogDB:
    audit_log = AuditLogDB(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        actor_user_id=_actor_id(current_user),
        actor_role=current_user.role,
        customer_id=customer_id,
        details=details or {},
    )
    db.add(audit_log)
    return audit_log


def serialize_audit_log(log: AuditLogDB) -> Dict[str, Any]:
    return {
        "id": log.id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "status": log.status,
        "actor_user_id": log.actor_user_id,
        "actor_role": log.actor_role,
        "customer_id": log.customer_id,
        "details": log.details or {},
        "created_at": log.created_at,
    }


@router.get("/", response_model=List[Dict[str, Any]])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    customer_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lists DB-backed admin audit logs, scoped by tenant for admins."""
    stmt = select(AuditLogDB)

    if current_user.role == "system_admin":
        if customer_id is not None:
            stmt = stmt.where(AuditLogDB.customer_id == customer_id)
    elif current_user.customer_id is not None:
        stmt = stmt.where(AuditLogDB.customer_id == current_user.customer_id)
    else:
        raise HTTPException(status_code=403, detail="Tenant admin is missing a customer scope")

    if action:
        stmt = stmt.where(AuditLogDB.action == action)

    stmt = stmt.order_by(desc(AuditLogDB.created_at)).limit(limit)
    result = await db.execute(stmt)
    return [serialize_audit_log(log) for log in result.scalars().all()]
