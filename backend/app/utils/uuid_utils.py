# ==============================================================================
# BLOCK COMMENT: UUIDV7 UTILITY - THIN WRAPPER AROUND uuid_utils PACKAGE
# Module: backend/app/utils/uuid_utils.py
# Description:
#     Provides generate_uuidv7() using the installed uuid_utils package
#     (Rust-based, RFC 9562 compliant, already in requirements.txt).
#     Falls back to uuid_extensions if uuid_utils is unavailable.
# ==============================================================================

import uuid

try:
    from uuid_utils import uuid7 as _uuid7
except ImportError:
    from uuid_extensions import uuid7 as _uuid7  # type: ignore[no-redef]


def generate_uuidv7() -> str:
    """Return a new RFC 9562 UUIDv7 string (time-ordered, monotonic)."""
    return str(_uuid7())


def is_valid_uuid(val: str) -> bool:
    """Validate if a string is a valid UUID format."""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
