from __future__ import annotations

from datetime import datetime, timezone

from app.jobs.enums import JobStatus
from app.models.db_models import JobDB
from app.repositories.job_repository import JobRepository


class JobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def create_job(
        self,
        *,
        customer_id: int,
        job_type,
        entity_type,
        entity_id: int | None = None,
        created_by: int | None = None,
        metadata: dict | None = None,
    ) -> JobDB:
        job = JobDB(
            customer_id=customer_id,
            job_type=job_type,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by=created_by,
            job_metadata=metadata or {},
            status=JobStatus.QUEUED,
            progress=0,
        )

        return await self.repository.create(job)

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
            return None

        job.status = JobStatus.RUNNING
        job.progress = 1
        job.started_at = datetime.now(timezone.utc)
        job.message = message

        return await self.repository.save(job)

    async def update_progress(
        self,
        job_id: int,
        progress: int,
        message: str | None = None,
    ):
        progress = max(0, min(progress, 100))
        job = await self.repository.get(job_id)

        if job is None:
            return None

        job.progress = progress

        if message:
            job.message = message

        return await self.repository.save(job)

    async def complete(
        self,
        job_id: int,
        message: str = "Completed",
    ):
        job = await self.repository.get(job_id)

        if job is None:
            return None

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        job.message = message

        return await self.repository.save(job)

    async def fail(
        self,
        job_id: int,
        error: str,
    ):
        job = await self.repository.get(job_id)

        if job is None:
            return None

        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now(timezone.utc)

        return await self.repository.save(job)

    async def cancel(
        self,
        job_id: int,
        message: str = "Cancelled",
    ):
        job = await self.repository.get(job_id)

        if job is None:
            return None

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.message = message

        return await self.repository.save(job)

    async def delete(
        self,
        job_id: int,
    ):
        return await self.repository.delete(job_id)
