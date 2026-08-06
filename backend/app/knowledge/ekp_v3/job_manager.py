"""
===============================================================================
BLOCK COMMENT: EKP V3 JOB MANAGER
Module: backend/app/knowledge/ekp_v3/job_manager.py
Author: EKP Architecture Team
Description:
    Manages background processing jobs (ekp_jobs) tracking document ingestion
    worker tasks, retry status, worker IDs, and execution metrics.
===============================================================================
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog
from app.models.db_models import EKPJobDB, EKPDocumentDB

logger = structlog.get_logger(__name__)


class EKPJobManager:
    """Manages background processing jobs for EKP V3 2-phase pipeline."""

    @staticmethod
    def create_job(db: Session, *, document_id: str, job_type: str = "INGESTION_PARSING") -> EKPJobDB:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job = EKPJobDB(
            id=job_id,
            document_id=document_id,
            job_type=job_type,
            status="QUEUED",
            retry_count=0
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("ekp_job_created", job_id=job_id, document_id=document_id, job_type=job_type)
        return job

    @staticmethod
    async def async_create_job(db: AsyncSession, *, document_id: str, job_type: str = "INGESTION_PARSING") -> EKPJobDB:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job = EKPJobDB(
            id=job_id,
            document_id=document_id,
            job_type=job_type,
            status="QUEUED",
            retry_count=0
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        logger.info("ekp_job_created_async", job_id=job_id, document_id=document_id, job_type=job_type)
        return job

    @staticmethod
    def mark_running(db: Session, job_id: str, worker_id: str = "worker-local-01"):
        job = db.query(EKPJobDB).filter(EKPJobDB.id == job_id).first()
        if job:
            job.status = "RUNNING"
            job.worker_id = worker_id
            job.started_at = datetime.utcnow()
            db.commit()
            logger.info("ekp_job_started", job_id=job_id, worker_id=worker_id)
        else:
            logger.warning("ekp_job_start_failed_not_found", job_id=job_id)

    @staticmethod
    async def async_mark_running(db: AsyncSession, job_id: str, worker_id: str = "worker-local-01"):
        res = await db.execute(select(EKPJobDB).where(EKPJobDB.id == job_id))
        job = res.scalars().first()
        if job:
            job.status = "RUNNING"
            job.worker_id = worker_id
            job.started_at = datetime.utcnow()
            await db.commit()
            logger.info("ekp_job_started_async", job_id=job_id, worker_id=worker_id)
        else:
            logger.warning("ekp_job_start_failed_not_found_async", job_id=job_id)

    @staticmethod
    def mark_completed(db: Session, job_id: str):
        job = db.query(EKPJobDB).filter(EKPJobDB.id == job_id).first()
        if job:
            job.status = "COMPLETED"
            job.finished_at = datetime.utcnow()
            db.commit()
            logger.info("ekp_job_completed", job_id=job_id)
        else:
            logger.warning("ekp_job_complete_failed_not_found", job_id=job_id)

    @staticmethod
    async def async_mark_completed(db: AsyncSession, job_id: str):
        res = await db.execute(select(EKPJobDB).where(EKPJobDB.id == job_id))
        job = res.scalars().first()
        if job:
            job.status = "COMPLETED"
            job.finished_at = datetime.utcnow()
            await db.commit()
            logger.info("ekp_job_completed_async", job_id=job_id)
        else:
            logger.warning("ekp_job_complete_failed_not_found_async", job_id=job_id)

    @staticmethod
    def mark_failed(db: Session, job_id: str, error_msg: str):
        job = db.query(EKPJobDB).filter(EKPJobDB.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.error_log = error_msg
            job.finished_at = datetime.utcnow()
            db.commit()
            logger.error("ekp_job_failed", job_id=job_id, error=error_msg)
        else:
            logger.warning("ekp_job_fail_failed_not_found", job_id=job_id)

    @staticmethod
    async def async_mark_failed(db: AsyncSession, job_id: str, error_msg: str):
        res = await db.execute(select(EKPJobDB).where(EKPJobDB.id == job_id))
        job = res.scalars().first()
        if job:
            job.status = "FAILED"
            job.error_log = error_msg
            job.finished_at = datetime.utcnow()
            await db.commit()
            logger.error("ekp_job_failed_async", job_id=job_id, error=error_msg)
        else:
            logger.warning("ekp_job_fail_failed_not_found_async", job_id=job_id)

