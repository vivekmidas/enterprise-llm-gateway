from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobListResponse, JobResponse
from app.services.job_service import JobService

router = APIRouter(
    prefix="/api/jobs",
    tags=["Jobs"],
)

def get_service(db: AsyncSession) -> JobService:
    return JobService(JobRepository(db))


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):

    service = get_service(db)

    jobs = await service.list_jobs(
        status=status,
        limit=limit,
        offset=offset,
    )

    total = await service.count_jobs(status=status)

    return JobListResponse(
        total=total,
        items=[JobResponse.model_validate(i) for i in jobs],
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):

    service = get_service(db)

    job = await service.get_job(job_id)

    if job is None:
        raise HTTPException(404, "Job not found")

    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):

    service = get_service(db)

    job = await service.cancel(job_id)

    if job is None:
        raise HTTPException(404, "Job not found")

    return {"success": True}


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):

    service = get_service(db)

    deleted = await service.delete(job_id)

    if not deleted:
        raise HTTPException(404, "Job not found")

    return {"success": True}