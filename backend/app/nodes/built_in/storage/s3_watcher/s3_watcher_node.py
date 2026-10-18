"""
===============================================================================
BLOCK COMMENT: S3 WATCHER NODE (EPIC-RAG-003 / STORY-3.7)
Module: backend/app/nodes/built_in/storage/s3_watcher_node.py
Description:
    BaseNode subclass for discovering and viewing S3 documents, tracking
    ingestion sync state via IngestionSourceLedgerDB, and feeding new/amended
    files into downstream workflow pipelines (e.g. RAGIngestionNode).
    - Category: Data Sources
    - Group: Storage
    - Connects to AWS S3 (or S3-compatible storage like MinIO/LocalStack)
    - Sync ledger prevents re-reading unchanged files based on ETag / SHA-256
    - Emits pipeline payloads formatted for RAGIngestionNode intake
===============================================================================
"""

import asyncio
import base64
import hashlib
import mimetypes
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode
from app.models.db_models import IngestionSourceLedgerDB

logger = structlog.get_logger(__name__)

# Fallback MIME mappings
_MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".html": "text/html",
    ".xml": "application/xml",
}

_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".tsv", ".html", ".xml", ".yaml", ".yml"}


def _guess_mime_type(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    if ext in _MIME_MAP:
        return _MIME_MAP[ext]
    guess, _ = mimetypes.guess_type(filename)
    return guess or "application/octet-stream"


class S3WatcherNode(BaseNode):
    """
    Workflow trigger & data source node for monitoring S3 buckets and streaming
    new/modified documents to RAG ingestion pipelines.
    """







    async def init(self) -> None:
        try:
            await super().init()
            self.logger.info("s3_watcher_node_init_completed", node_name=self.name)
        except Exception:
            self.logger.exception("s3_watcher_node_init_failed", node_name=self.name)
            raise

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[str]:
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        cid = user_data.get("customer_id") if user_data.get("customer_id") is not None else context.get("customer_id")
        return str(cid) if cid is not None else None

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        data = self.get_input_data(inp)
        if not isinstance(data, dict):
            return self._validation_error(inp, "S3 Watcher input must be a JSON object.")

        bucket_name = data.get("bucket_name") or inp.config.get("bucket_name")
        if not bucket_name or not str(bucket_name).strip():
            return self._validation_error(inp, "bucket_name is required in configuration or input.")

        customer_id = self._resolve_customer_id(inp)
        if not customer_id:
            return self._validation_error(inp, "customer_id is required in execution context for tenant segregation.")

        return None

    def _validation_error(self, inp: NodeInput, message: str) -> NodeOutput:
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="failure",
            error_code=400,
            error_message=message,
            violations=["validation_error"],
        )

    def _get_s3_client(self, config: Dict[str, Any], data: Dict[str, Any]):
        """
        Resolves or creates S3 client.
        Supports injected mock client for test environments or boto3 client for production.
        """
        # 1. Check for directly injected test client
        if "mock_s3_client" in config:
            return config["mock_s3_client"]
        if "mock_s3_client" in data:
            return data["mock_s3_client"]

        # 2. Dynamic import of boto3
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 is not installed. Please install boto3 or provide mock_s3_client for testing.")

        aws_region = data.get("aws_region") or config.get("aws_region") or "us-east-1"
        aws_access_key = data.get("aws_access_key_id") or config.get("aws_access_key_id")
        aws_secret_key = data.get("aws_secret_access_key") or config.get("aws_secret_access_key")
        endpoint_url = data.get("endpoint_url") or config.get("endpoint_url")

        client_kwargs = {"region_name": aws_region}
        if aws_access_key and aws_secret_key:
            client_kwargs["aws_access_key_id"] = aws_access_key
            client_kwargs["aws_secret_access_key"] = aws_secret_key
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        return boto3.client("s3", **client_kwargs)

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Lists S3 objects, evaluates sync ledger, downloads new/modified files,
        updates IngestionSourceLedgerDB, and outputs formatted payload.
        """
        data = self.get_input_data(inp)
        customer_id = self._resolve_customer_id(inp)
        if not customer_id:
            return self._validation_error(inp, "customer_id is required for S3 watcher execution.")

        bucket_name = str(data.get("bucket_name") or inp.config.get("bucket_name", "")).strip()
        prefix = str(data.get("prefix") or inp.config.get("prefix", "")).strip()
        target_kb_id = data.get("knowledge_base_id") or inp.config.get("knowledge_base_id")
        target_kb_id = str(target_kb_id).strip() if target_kb_id else None
        force_resync = bool(data.get("force_resync") or inp.config.get("force_resync", False))

        max_files = int(data.get("max_files_per_run") or inp.config.get("max_files_per_run", 10))
        ext_str = str(data.get("include_extensions") or inp.config.get("include_extensions", ".pdf, .docx, .txt, .md, .json"))
        allowed_extensions = {ext.strip().lower() for ext in ext_str.split(",") if ext.strip()}

        # Initialize S3 client
        try:
            s3_client = self._get_s3_client(inp.config, data)
        except Exception as e:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=500,
                error_message=f"Failed to initialize S3 client: {str(e)}",
            )

        # List objects from S3
        try:
            s3_objects = await self._list_s3_objects(s3_client, bucket_name, prefix)
        except Exception as e:
            self.logger.error("s3_list_objects_failed", bucket=bucket_name, prefix=prefix, error=str(e))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=500,
                error_message=f"Failed to list S3 objects in s3://{bucket_name}/{prefix}: {str(e)}",
            )

        # Filter by allowed extensions and ignore directory marker keys
        matching_objects = []
        for obj in s3_objects:
            key = obj.get("Key", "")
            if not key or key.endswith("/"):
                continue
            _, ext = os.path.splitext(key.lower())
            if allowed_extensions and ext not in allowed_extensions:
                continue
            matching_objects.append(obj)

        total_found = len(matching_objects)
        processed_documents: List[Dict[str, Any]] = []
        file_summaries: List[Dict[str, Any]] = []
        processed_count = 0
        skipped_count = 0

        # Query and update ledger
        async with AsyncSessionLocal() as db:
            for obj in matching_objects:
                key = obj["Key"]
                etag = str(obj.get("ETag", "")).strip('"')
                size = obj.get("Size", 0)
                last_modified_raw = obj.get("LastModified")

                # Normalize last_modified to datetime
                if isinstance(last_modified_raw, str):
                    try:
                        last_modified_dt = datetime.fromisoformat(last_modified_raw.replace("Z", "+00:00"))
                    except Exception:
                        last_modified_dt = datetime.now(timezone.utc)
                elif isinstance(last_modified_raw, datetime):
                    last_modified_dt = last_modified_raw
                else:
                    last_modified_dt = datetime.now(timezone.utc)

                source_uri = f"s3://{bucket_name}/{key}"

                # Query existing ledger entry
                ledger_stmt = select(IngestionSourceLedgerDB).where(
                    IngestionSourceLedgerDB.customer_id == str(customer_id),
                    IngestionSourceLedgerDB.source_uri == source_uri,
                )
                ledger_res = await db.execute(ledger_stmt)
                ledger_entry: Optional[IngestionSourceLedgerDB] = ledger_res.scalars().first()

                is_unchanged = False
                if ledger_entry and not force_resync:
                    if ledger_entry.etag and ledger_entry.etag == etag:
                        is_unchanged = True

                if is_unchanged:
                    skipped_count += 1
                    file_summaries.append({
                        "key": key,
                        "source_uri": source_uri,
                        "size": size,
                        "etag": etag,
                        "status": "skipped",
                    })
                    continue

                # Stop if max_files limit reached
                if processed_count >= max_files:
                    file_summaries.append({
                        "key": key,
                        "source_uri": source_uri,
                        "size": size,
                        "etag": etag,
                        "status": "limit_reached",
                    })
                    continue

                # Fetch object content
                try:
                    raw_bytes = await self._get_s3_object_bytes(s3_client, bucket_name, key)
                except Exception as e:
                    self.logger.error("s3_get_object_failed", bucket=bucket_name, key=key, error=str(e))
                    file_summaries.append({
                        "key": key,
                        "source_uri": source_uri,
                        "size": size,
                        "etag": etag,
                        "status": "fetch_failed",
                        "error": str(e),
                    })
                    continue

                file_hash = hashlib.sha256(raw_bytes).hexdigest()
                mime_type = _guess_mime_type(key)
                _, ext = os.path.splitext(key.lower())

                # Format content: raw text if text file, Base64 data URI if binary
                if ext in _TEXT_EXTENSIONS:
                    try:
                        content_str = raw_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        content_str = f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"
                else:
                    content_str = f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"

                filename = os.path.basename(key)
                doc_metadata = {
                    "bucket": bucket_name,
                    "key": key,
                    "etag": etag,
                    "file_size": len(raw_bytes),
                    "last_modified": last_modified_dt.isoformat() if hasattr(last_modified_dt, "isoformat") else str(last_modified_dt),
                }

                # Upsert ledger entry
                is_new = False
                if not ledger_entry:
                    is_new = True
                    ledger_entry = IngestionSourceLedgerDB(
                        customer_id=str(customer_id),
                        knowledge_base_id=target_kb_id,
                        source_uri=source_uri,
                        source_type="s3",
                        file_hash=file_hash,
                        etag=etag,
                        sync_status="synced",
                        last_modified=last_modified_dt,
                        document_version=1,
                    )
                    db.add(ledger_entry)
                else:
                    ledger_entry.file_hash = file_hash
                    ledger_entry.etag = etag
                    ledger_entry.last_modified = last_modified_dt
                    ledger_entry.sync_status = "synced"
                    ledger_entry.document_version = (ledger_entry.document_version or 1) + 1
                    if target_kb_id:
                        ledger_entry.knowledge_base_id = target_kb_id
                    db.add(ledger_entry)

                await db.commit()
                await db.refresh(ledger_entry)

                doc_payload = {
                    "document_content": content_str,
                    "document_name": filename,
                    "source_uri": source_uri,
                    "source_type": "s3",
                    "mime_type": mime_type,
                    "knowledge_base_id": target_kb_id,
                    "document_version": ledger_entry.document_version,
                    "metadata": doc_metadata,
                }
                processed_documents.append(doc_payload)
                processed_count += 1

                file_summaries.append({
                    "key": key,
                    "source_uri": source_uri,
                    "size": len(raw_bytes),
                    "etag": etag,
                    "status": "new" if is_new else "modified",
                    "version": ledger_entry.document_version,
                })

        # Primary single document payload (for direct node-to-node pipelining into RAGIngestionNode)
        primary_doc = processed_documents[0] if processed_documents else {}

        output_data = {
            "document_content": primary_doc.get("document_content"),
            "document_name": primary_doc.get("document_name"),
            "source_uri": primary_doc.get("source_uri"),
            "source_type": "s3",
            "mime_type": primary_doc.get("mime_type"),
            "knowledge_base_id": target_kb_id,
            "metadata": primary_doc.get("metadata") or {},
            "documents": processed_documents,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "total_found": total_found,
            "files": file_summaries,
        }

        self.logger.info(
            "s3_watcher_execution_completed",
            bucket=bucket_name,
            prefix=prefix,
            processed=processed_count,
            skipped=skipped_count,
            total=total_found,
        )

        return NodeOutput(
            trace_id=inp.trace_id,
            data=self.set_output_data(inp, output_data),
        )

    async def _list_s3_objects(self, s3_client: Any, bucket: str, prefix: str) -> List[Dict[str, Any]]:
        """Asynchronously lists objects from S3 client."""
        if hasattr(s3_client, "list_objects_v2_async"):
            res = await s3_client.list_objects_v2_async(Bucket=bucket, Prefix=prefix)
            return res.get("Contents", [])

        # Sync boto3 client wrapped in asyncio.to_thread
        def _sync_list():
            kwargs = {"Bucket": bucket}
            if prefix:
                kwargs["Prefix"] = prefix
            res = s3_client.list_objects_v2(**kwargs)
            return res.get("Contents", [])

        return await asyncio.to_thread(_sync_list)

    async def _get_s3_object_bytes(self, s3_client: Any, bucket: str, key: str) -> bytes:
        """Asynchronously reads object body bytes from S3 client."""
        if hasattr(s3_client, "get_object_async"):
            res = await s3_client.get_object_async(Bucket=bucket, Key=key)
            body = res["Body"]
            if hasattr(body, "read_async"):
                return await body.read_async()
            return body.read() if hasattr(body, "read") else bytes(body)

        def _sync_get():
            res = s3_client.get_object(Bucket=bucket, Key=key)
            body = res["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)

        return await asyncio.to_thread(_sync_get)

    async def preview(self, inp: NodeInput) -> Dict[str, Any]:
        """
        Lightweight discovery method for visual canvas preview.
        Lists objects and sync status against ledger without downloading object bodies.
        """
        data = self.get_input_data(inp)
        customer_id = self._resolve_customer_id(inp)
        bucket_name = str(data.get("bucket_name") or inp.config.get("bucket_name", "")).strip()
        prefix = str(data.get("prefix") or inp.config.get("prefix", "")).strip()
        ext_str = str(data.get("include_extensions") or inp.config.get("include_extensions", ".pdf, .docx, .txt, .md, .json"))
        allowed_extensions = {ext.strip().lower() for ext in ext_str.split(",") if ext.strip()}

        s3_client = self._get_s3_client(inp.config, data)
        s3_objects = await self._list_s3_objects(s3_client, bucket_name, prefix)

        results = []
        async with AsyncSessionLocal() as db:
            for obj in s3_objects:
                key = obj.get("Key", "")
                if not key or key.endswith("/"):
                    continue
                _, ext = os.path.splitext(key.lower())
                if allowed_extensions and ext not in allowed_extensions:
                    continue

                etag = str(obj.get("ETag", "")).strip('"')
                size = obj.get("Size", 0)
                source_uri = f"s3://{bucket_name}/{key}"

                status = "new"
                if customer_id:
                    stmt = select(IngestionSourceLedgerDB).where(
                        IngestionSourceLedgerDB.customer_id == str(customer_id),
                        IngestionSourceLedgerDB.source_uri == source_uri,
                    )
                    entry = (await db.execute(stmt)).scalars().first()
                    if entry:
                        status = "synced" if entry.etag == etag else "modified"

                results.append({
                    "key": key,
                    "source_uri": source_uri,
                    "size": size,
                    "etag": etag,
                    "status": status,
                })

        return {
            "bucket": bucket_name,
            "prefix": prefix,
            "total": len(results),
            "files": results,
        }

