from typing import Any

def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely casts any value to an integer. 
    Returns default if value is None, empty string, or cannot be parsed.
    """
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely casts any value to a float.
    Returns default if value is None, empty string, or cannot be parsed.
    """
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
