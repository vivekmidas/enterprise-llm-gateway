from dataclasses import dataclass
from typing import Any

from .enums import JobStatus
from .enums import JobType
from .enums import EntityType


@dataclass(slots=True)
class JobContext:

    job_id: int

    customer_id: int

    job_type: JobType

    entity_type: EntityType

    entity_id: int | None

    trace_id: str

    metadata: dict[str, Any]