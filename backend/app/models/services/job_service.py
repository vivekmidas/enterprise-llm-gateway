from __future__ import annotations

from datetime import datetime, timezone
import structlog

from app.models.db_models import JobDB
from app.jobs.enums import JobStatus
from app.repositories.job_repository import JobRepository

logger = structlog.get_logger(__name__)


class JobService:

    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def create_job(
        self,
        *,
        customer_id: str,
        job_type,
        entity_type,
        entity_id: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> JobDB:

        job = JobDB(
            customer_id=customer_id,
            job_type=job_type,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by=created_by,
            metadata=metadata or {},
            status=JobStatus.QUEUED,
            progress=0,
        )

        created = await self.repository.create(job)
        logger.info(
            "job_created",
            job_id=str(created.id),
            customer_id=str(customer_id),
            job_type=str(job_type),
            entity_type=str(entity_type),
            entity_id=str(entity_id),
        )
        return created

    async def get_job(self, job_id: int):
        return await self.repository.get(job_id)

    async def list_jobs(
        self,
        *,
        status=None,
        limit=50,
        offset=0,
    ):
        return await self.repository.list_jobs(
            status=status,
            limit=limit,
            offset=offset,
        )

    async def count_jobs(
        self,
        *,
        status=None,
    ):
        return await self.repository.count_jobs(status=status)

    async def start(
        self,
        job_id: int,
        message: str = "Started",
    ):

        job = await self.repository.get(job_id)

        if job is None:
            logger.warning("job_start_failed_not_found", job_id=str(job_id))
            return None

        job.status = JobStatus.RUNNING
        job.progress = 1
        job.started_at = datetime.now(timezone.utc)
        job.message = message

        saved = await self.repository.save(job)
        logger.info("job_started", job_id=str(job_id), message=message)
        return saved

    async def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str | None = None,
    ):

        progress = max(0, min(progress, 100))

        job = await self.repository.get(job_id)

        if job is None:
            logger.warning("job_progress_update_failed_not_found", job_id=str(job_id))
            return None

        job.progress = progress

        if message:
            job.message = message

        saved = await self.repository.save(job)
        logger.info("job_progress_updated", job_id=str(job_id), progress=progress, message=message)
        return saved

    async def complete(
        self,
        job_id: int,
        message: str = "Completed",
    ):

        job = await self.repository.get(job_id)

        if job is None:
            logger.warning("job_complete_failed_not_found", job_id=str(job_id))
            return None

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        job.message = message

        saved = await self.repository.save(job)
        logger.info("job_completed", job_id=str(job_id), message=message)
        return saved

    async def fail(
        self,
        job_id: int,
        error: str,
    ):

        job = await self.repository.get(job_id)

        if job is None:
            logger.warning("job_fail_failed_not_found", job_id=str(job_id))
            return None

        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now(timezone.utc)

        saved = await self.repository.save(job)
        logger.error("job_failed", job_id=str(job_id), error=error)
        return saved

    async def cancel(
        self,
        job_id: int,
        message: str = "Cancelled",
    ):

        job = await self.repository.get(job_id)

        if job is None:
            logger.warning("job_cancel_failed_not_found", job_id=str(job_id))
            return None

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.message = message

        saved = await self.repository.save(job)
        logger.info("job_cancelled", job_id=str(job_id), message=message)
        return saved

    async def delete(
        self,
        job_id: int,
    ):
        logger.info("job_deleted", job_id=str(job_id))
        return await self.repository.delete(job_id)