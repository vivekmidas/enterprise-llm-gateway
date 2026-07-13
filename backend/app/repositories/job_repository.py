from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import JobDB


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, job: JobDB) -> JobDB:
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def save(self, job: JobDB) -> JobDB:
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get(self, job_id: int):
        return await self.db.get(JobDB, job_id)

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        stmt = select(JobDB)

        if status:
            stmt = stmt.where(JobDB.status == status)

        stmt = stmt.order_by(JobDB.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)

        return result.scalars().all()

    async def count_jobs(
        self,
        *,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count(JobDB.id))

        if status:
            stmt = stmt.where(JobDB.status == status)

        result = await self.db.execute(stmt)

        return result.scalar_one()

    async def delete(self, job_id: int) -> bool:
        job = await self.get(job_id)

        if job is None:
            return False

        await self.db.delete(job)
        await self.db.commit()

        return True

    async def update_progress(
        self,
        *,
        job_id: int,
        progress: int,
        message: str | None = None,
    ):
        job = await self.get(job_id)

        if job is None:
            return None

        job.progress = progress

        if message is not None:
            job.message = message

        await self.save(job)

        return job

    async def update_status(
        self,
        *,
        job_id: int,
        status: str,
        message: str | None = None,
    ):
        job = await self.get(job_id)

        if job is None:
            return None

        job.status = status

        if message is not None:
            job.message = message

        await self.save(job)

        return job
