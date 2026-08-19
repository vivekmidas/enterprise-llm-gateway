from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | int
    job_type: str
    status: str
    progress: int
    message: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str | int] = None
    customer_id: Optional[str | int] = None
    created_by: Optional[str | int] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobListResponse(BaseModel):
    total: int
    items: list[JobResponse]


class JobCancelResponse(BaseModel):
    success: bool
