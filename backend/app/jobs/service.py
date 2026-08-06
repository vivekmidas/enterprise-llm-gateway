from typing import Optional
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.enums import EntityType, JobStatus, JobType
from app.jobs.repository import JobRepository
from app.models.db_models import JobDB

logger = structlog.get_logger(__name__)


class JobService:

    def __init__(self):
        self.repo = JobRepository()

    async def create_job(
        self,
        db: AsyncSession,
        *,
        customer_id: int,
        job_type: JobType,
        entity_type: EntityType,
        entity_id: int | None = None,
        metadata: dict | None = None,
        created_by: int | None = None,
    ) -> JobDB:

        job = await self.repo.create(
            db,
            customer_id=customer_id,
            job_type=job_type,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
            created_by=created_by,
        )
        logger.info(
            "job_created",
            job_id=str(job.id),
            customer_id=customer_id,
            job_type=str(job_type),
            entity_type=str(entity_type),
            entity_id=entity_id,
        )
        return job

    async def start_job(
        self,
        db: AsyncSession,
        job_id: int,
        message: str | None = None,
    ) -> JobDB | None:

        job = await self.repo.start(
            db,
            job_id=job_id,
            message=message,
        )
        if job:
            logger.info("job_started", job_id=str(job_id), message=message)
        else:
            logger.warning("job_start_failed_not_found", job_id=str(job_id))
        return job

    async def update_progress(
        self,
        db: AsyncSession,
        job_id: int,
        progress: int,
        message: str | None = None,
    ) -> JobDB | None:

        progress = max(0, min(progress, 100))

        job = await self.repo.update_progress(
            db,
            job_id=job_id,
            progress=progress,
            message=message,
        )
        if job:
            logger.info("job_progress_updated", job_id=str(job_id), progress=progress, message=message)
        else:
            logger.warning("job_progress_update_failed_not_found", job_id=str(job_id))
        return job

    async def complete_job(
        self,
        db: AsyncSession,
        job_id: int,
        message: str | None = None,
    ) -> JobDB | None:

        job = await self.repo.complete(
            db,
            job_id=job_id,
            message=message,
        )
        if job:
            logger.info("job_completed", job_id=str(job_id), message=message)
        else:
            logger.warning("job_complete_failed_not_found", job_id=str(job_id))
        return job

    async def fail_job(
        self,
        db: AsyncSession,
        job_id: int,
        error: str,
    ) -> JobDB | None:

        job = await self.repo.fail(
            db,
            job_id=job_id,
            error=error,
        )
        if job:
            logger.error("job_failed", job_id=str(job_id), error=error)
        else:
            logger.warning("job_fail_failed_not_found", job_id=str(job_id))
        return job

    async def cancel_job(
        self,
        db: AsyncSession,
        job_id: int,
    ) -> JobDB | None:

        job = await self.repo.cancel(
            db,
            job_id=job_id,
        )
        if job:
            logger.info("job_cancelled", job_id=str(job_id))
        else:
            logger.warning("job_cancel_failed_not_found", job_id=str(job_id))
        return job

    async def get_job(
        self,
        db: AsyncSession,
        job_id: int,
    ) -> Optional[JobDB]:

        return await self.repo.get(
            db,
            job_id,
        )

    async def list_jobs(
        self,
        db: AsyncSession,
        *,
        customer_id: int | None = None,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        entity_type: EntityType | None = None,
        limit: int = 100,
        offset: int = 0,
    ):

        return await self.repo.list(
            db,
            customer_id=customer_id,
            status=status,
            job_type=job_type,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )