"""
===============================================================================
BLOCK COMMENT: EKP V3 INDEPENDENT BACKGROUND WORKER & CRON SWEEPER
Module: backend/app/knowledge/ekp_v3/worker.py
Author: EKP Architecture Team
Description:
    Independent background worker and cron sweeper daemon. Periodically sweeps
    unprocessed or QUEUED document ingestion jobs from the database and executes
    parsing, paragraph extraction, domain entity extraction, and vector indexing
    as an autonomous process.
===============================================================================
"""

import asyncio
import structlog
from typing import List
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.db_models import EKPDocumentDB, EKPJobDB
from app.knowledge.ekp_v3.job_manager import EKPJobManager
from app.knowledge.ekp_v3.pipeline_v3 import EKPProcessingPipeline

logger = structlog.get_logger(__name__)
pipeline = EKPProcessingPipeline()


async def sweep_and_process_pending_jobs_async() -> int:
    """Sweeps all UPLOADED documents & QUEUED jobs, processing them asynchronously."""
    processed_count = 0
    async with AsyncSessionLocal() as db:
        try:
            # 1. Sweep UPLOADED documents without queued jobs
            doc_stmt = select(EKPDocumentDB).where(EKPDocumentDB.processing_stage == "UPLOADED")
            doc_res = await db.execute(doc_stmt)
            uploaded_docs = doc_res.scalars().all()

            for doc in uploaded_docs:
                job_stmt = select(EKPJobDB).where(EKPJobDB.document_id == doc.id, EKPJobDB.status.in_(["QUEUED", "RUNNING"]))
                job_res = await db.execute(job_stmt)
                existing_job = job_res.scalars().first()

                if not existing_job:
                    job = await EKPJobManager.async_create_job(db, document_id=doc.id, job_type="INGESTION_PARSING")
                    asyncio.create_task(pipeline.process_document_job_async(job.id))
                    processed_count += 1

            # 2. Sweep remaining QUEUED jobs
            queued_stmt = select(EKPJobDB).where(EKPJobDB.status == "QUEUED")
            queued_res = await db.execute(queued_stmt)
            queued_jobs = queued_res.scalars().all()

            for job in queued_jobs:
                asyncio.create_task(pipeline.process_document_job_async(job.id))
                processed_count += 1

        except Exception as e:
            logger.error("ekp_worker_sweep_failed", error=str(e))

    if processed_count > 0:
        logger.info("ekp_worker_jobs_dispatched", processed_count=processed_count)

    return processed_count


async def start_background_cron_loop(interval_seconds: int = 30):
    """Periodic independent background daemon sweeping for new documents every N seconds."""
    logger.info("ekp_worker_cron_loop_started", interval_seconds=interval_seconds)
    while True:
        try:
            await sweep_and_process_pending_jobs_async()
        except Exception as e:
            logger.error("ekp_worker_cron_error", error=str(e))
        await asyncio.sleep(interval_seconds)
