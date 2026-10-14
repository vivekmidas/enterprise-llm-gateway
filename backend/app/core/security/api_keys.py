# ===============================================================================
# BLOCK COMMENT: CRYPTOGRAPHIC API KEY UTILITIES & VERIFICATION (EPIC-AUTH-001 / STORY-1.2)
# Module: backend/app/core/security/api_keys.py
# Description:
#     Provides cryptographic API key generation, constant-time SHA-256 hashing,
#     and async database lookup for multi-tenant service credentials.
#     Raw keys are formatted as: gw_live_<32_random_chars>.
# ===============================================================================

import hashlib
import hmac
import secrets
from typing import Optional, Tuple
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import APIKeyDB


KEY_PREFIX = "gw_live_"


def generate_api_key(prefix: str = KEY_PREFIX) -> Tuple[str, str, str]:
    """
    Generates a cryptographically secure API key.
    
    Returns:
        Tuple of (plaintext_key, key_prefix, key_hash)
        - plaintext_key: Full raw token (e.g. 'gw_live_k8J9m2...'). Shown ONCE to user.
        - key_prefix: First 16 characters for identification in admin UI.
        - key_hash: Deterministic SHA-256 hex string (64 chars) stored in DB.
    """
    random_part = secrets.token_urlsafe(32)
    plaintext_key = f"{prefix}{random_part}"
    key_prefix = plaintext_key[:16]
    key_hash = hash_api_key(plaintext_key)
    return plaintext_key, key_prefix, key_hash


def hash_api_key(plaintext_key: str) -> str:
    """Computes deterministic SHA-256 hex string for an API key."""
    if not plaintext_key:
        return ""
    return hashlib.sha256(plaintext_key.strip().encode("utf-8")).hexdigest()


def verify_api_key_hash(plaintext_key: str, expected_hash: str) -> bool:
    """Constant-time verification of plaintext key against stored SHA-256 hash."""
    if not plaintext_key or not expected_hash:
        return False
    computed_hash = hash_api_key(plaintext_key)
    return hmac.compare_digest(computed_hash, expected_hash)


async def lookup_api_key(db: AsyncSession, raw_key: str) -> Optional[APIKeyDB]:
    """
    Looks up and validates an active, non-expired APIKeyDB by its raw key string.
    
    Args:
        db: Active async database session.
        raw_key: Raw token from X-API-Key or Authorization header.
        
    Returns:
        APIKeyDB record if valid and active, else None.
    """
    if not raw_key or not str(raw_key).strip():
        return None

    hashed = hash_api_key(raw_key)
    stmt = select(APIKeyDB).where(
        APIKeyDB.key_hash == hashed,
        APIKeyDB.is_active == True,
    )
    result = await db.execute(stmt)
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj:
        return None

    # Check expiration if configured
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
        return None

    return api_key_obj


# Backward compatibility alias
async def verify_api_key(key: str, db: Optional[AsyncSession] = None) -> bool:
    """Legacy helper for backward compatibility."""
    if not key:
        return False
    if db is not None:
        key_obj = await lookup_api_key(db, key)
        return key_obj is not None
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        key_obj = await lookup_api_key(session, key)
        return key_obj is not None
