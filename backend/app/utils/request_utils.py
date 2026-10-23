# backend/app/utils/request_utils.py
# ==============================================================================
# BLOCK COMMENT: INBOUND REQUEST CAPTURE (WEBHOOK TRACEABILITY)
# Description:
#   Builds a sanitized, JSON-serializable snapshot of an inbound HTTP request.
#   Stored at WORKFLOW level as context["request"] (one per execution) so every
#   node can read it via NodeInput.context / Jinja ({{ request.client_ip }}) and it
#   is persisted with the trace. Not copied into trigger node metadata (avoids
#   duplication; downstream nodes would otherwise need the trigger node id).
#
#   IP capture (both kept, never merged):
#     - client_ip / client_port : socket peer (last hop, trustworthy).
#     - forwarded_ip + x_forwarded_for(_chain), x_real_ip, forwarded, ... :
#       client-supplied proxy headers (UNTRUSTED unless behind a trusted proxy).
#
#   Security: Authorization, Cookie, API keys and signature values are NEVER
#   captured. Query params with sensitive names are masked.
# ==============================================================================
import hashlib
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Request

from app.utils.time_utils import to_iso_utc

_SENSITIVE_KEY_RE = re.compile(r"(token|key|secret|signature|sig|password|passwd|pwd|auth|credential)", re.IGNORECASE)
_MASK = "***"

# Headers whose PRESENCE (not value) is recorded to indicate signed webhooks.
_SIGNATURE_HEADERS = (
    "x-hub-signature", "x-hub-signature-256", "x-signature", "x-webhook-signature",
    "stripe-signature", "x-slack-signature",
)


def _mask_query_params(request: Request) -> Dict[str, Any]:
    """Returns query params (multi-values as list) with sensitive keys masked."""
    out: Dict[str, Any] = {}
    for key in request.query_params.keys():
        values = request.query_params.getlist(key)
        if _SENSITIVE_KEY_RE.search(key):
            out[key] = _MASK
        else:
            out[key] = values[0] if len(values) == 1 else values
    return out


def _split_forwarded_for(value: Optional[str]) -> List[str]:
    """Splits an X-Forwarded-For header into an ordered list (client first)."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _auth_scheme(request: Request) -> str:
    """Detects auth scheme without capturing any credential value."""
    if request.headers.get("x-api-key"):
        return "api_key"
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return "api_key" if auth[7:].strip().startswith("gw_") else "bearer"
    if auth.lower().startswith("basic "):
        return "basic"
    return "none" if not auth else "other"


def extract_request_info(
    request: Request,
    body: Optional[bytes] = None,
    source: str = "webhook",
    trace_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Builds a sanitized snapshot of the inbound request.

    Args:
        request: FastAPI/Starlette request.
        body: Raw body bytes (for size + sha256; body itself is NOT stored here).
        source: Entry point label, e.g. "webhook" or "api".
        trace_id: Workflow trace id for cross-reference.
        extra: Additional routing/auth keys (workflow_id, agent_node_id, user_id, ...).
    """
    received_at = time.time()
    headers = request.headers
    xff_raw = headers.get("x-forwarded-for")
    xff_chain = _split_forwarded_for(xff_raw)

    info: Dict[str, Any] = {
        # Identity
        "request_id": headers.get("x-request-id") or headers.get("x-correlation-id") or uuid.uuid4().hex,
        "trace_id": trace_id,
        "source": source,
        # Time
        "received_at": received_at,
        "received_at_iso": to_iso_utc(received_at),
        # HTTP
        "method": request.method,
        "scheme": request.url.scheme,
        "http_version": request.scope.get("http_version"),
        "host": headers.get("host"),
        "path": request.url.path,
        "query_params": _mask_query_params(request),
        # Network: socket peer (trusted hop)
        "client_ip": request.client.host if request.client else None,
        "client_port": request.client.port if request.client else None,
        # Network: proxy-supplied (untrusted unless via trusted proxy)
        "forwarded_ip": xff_chain[0] if xff_chain else None,
        "x_forwarded_for": xff_raw,
        "x_forwarded_for_chain": xff_chain,
        "x_real_ip": headers.get("x-real-ip"),
        "forwarded": headers.get("forwarded"),
        "x_forwarded_proto": headers.get("x-forwarded-proto"),
        "x_forwarded_host": headers.get("x-forwarded-host"),
        "cf_connecting_ip": headers.get("cf-connecting-ip"),
        "true_client_ip": headers.get("true-client-ip"),
        # Client
        "user_agent": headers.get("user-agent"),
        "referer": headers.get("referer"),
        "origin": headers.get("origin"),
        "accept": headers.get("accept"),
        "accept_language": headers.get("accept-language"),
        # Payload (metadata only)
        "content_type": headers.get("content-type"),
        "content_length": headers.get("content-length"),
        "payload_size_bytes": len(body) if body is not None else None,
        "payload_sha256": hashlib.sha256(body).hexdigest() if body is not None else None,
        # Auth (no secrets)
        "auth_scheme": _auth_scheme(request),
        "has_signature_header": any(h in headers for h in _SIGNATURE_HEADERS),
        "idempotency_key": headers.get("idempotency-key") or headers.get("x-idempotency-key"),
    }
    if extra:
        info.update(extra)
    return info

