from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import EntityType
from .enums import JobStatus
from .enums import JobType


class JobCreate(BaseModel):

    customer_id: int

    job_type: JobType

    entity_type: EntityType

    entity_id: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_by: int | None = None


class JobUpdate(BaseModel):

    progress: int | None = None

    message: str | None = None

    error: str | None = None

    status: JobStatus | None = None


class JobResponse(BaseModel):

    id: int

    customer_id: int

    job_type: JobType

    entity_type: EntityType

    entity_id: int | None

    status: JobStatus

    progress: int

    message: str | None

    error: str | None

    metadata: dict[str, Any]

    started_at: datetime | None

    completed_at: datetime |None

    created_at: datetime

    updated_at: datetime