# ===============================================================================
# BLOCK COMMENT: RE-EXPORT FOR BACKWARD COMPATIBILITY (EPIC-AUTH-001 / STORY-1.1)
# Module: backend/app/models/api_keys.py
# Description:
#     Re-exports APIKeyDB as APIKey for backward-compatible imports across codebase.
# ===============================================================================
from app.models.db_models import APIKeyDB

# Backward compatibility alias
APIKey = APIKeyDB

__all__ = ["APIKeyDB", "APIKey"]