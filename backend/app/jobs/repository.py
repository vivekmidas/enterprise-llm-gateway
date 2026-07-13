from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.enums import JobStatus, JobType, EntityType
from app.models.db_models import JobDB


class JobRepository:

    async def create(
        self,
        db: AsyncSession,
        *,
        customer_id: int,
        job_type: JobType,
        entity_type: EntityType,
        entity_id: Optional[int] = None,
        metadata: Optional[dict] = None,
        created_by: Optional[int] = None,
    ) -> JobDB:

        job = JobDB(
            customer_id=customer_id,
            job_type=job_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status=JobStatus.QUEUED,
            progress=0,
            job_metadata=metadata or {},
            created_by=created_by,
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)

        return job

    async def get(
        self,
        db: AsyncSession,
        job_id: int,
    ) -> Optional[JobDB]:

        stmt = select(JobDB).where(JobDB.id == job_id)

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    async def list(
        self,
        db: AsyncSession,
        *,
        customer_id: Optional[int] = None,
        status: Optional[JobStatus] = None,
        job_type: Optional[JobType] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        offset: int = 0,
    ):

        stmt = select(JobDB)

        if customer_id is not None:
            stmt = stmt.where(JobDB.customer_id == customer_id)

        if isinstance(status, str):
            status = JobStatus(status)
            
        if job_type is not None:
            stmt = stmt.where(JobDB.job_type == job_type)

        if entity_type is not None:
            stmt = stmt.where(JobDB.entity_type == entity_type)

        stmt = (
            stmt.order_by(JobDB.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(stmt)

        return result.scalars().all()

    async def update_progress(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        progress: int,
        message: Optional[str] = None,
    ) -> Optional[JobDB]:

        job = await self.get(db, job_id)

        if not job:
            return None

        job.progress = max(0, min(progress, 100))

        if message:
            job.message = message

        await db.commit()
        await db.refresh(job)

        return job

    async def start(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        message: Optional[str] = None,
    ) -> Optional[JobDB]:

        job = await self.get(db, job_id)

        if not job:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)

        if message:
            job.message = message

        await db.commit()
        await db.refresh(job)

        return job

    async def complete(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        message: Optional[str] = None,
    ) -> Optional[JobDB]:

        job = await self.get(db, job_id)

        if not job:
            return None

        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)

        if message:
            job.message = message

        await db.commit()
        await db.refresh(job)

        return job

    async def fail(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        error: str,
    ) -> Optional[JobDB]:

        job = await self.get(db, job_id)

        if not job:
            return None

        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(job)

        return job

    async def cancel(
        self,
        db: AsyncSession,
        *,
        job_id: int,
    ) -> Optional[JobDB]:

        job = await self.get(db, job_id)

        if not job:
            return None

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(job)

        return job

    async def delete(
        self,
        db: AsyncSession,
        *,
        job_id: int,
    ) -> bool:

        job = await self.get(db, job_id)

        if not job:
            return False

        await db.delete(job)

        await db.commit()

        return True
