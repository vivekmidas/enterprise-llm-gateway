import json
from typing import Any

def try_parse_json(val: Any) -> Any:
    """
    Safely attempts to parse a value as JSON if it is a string.
    Returns the original value if it's not a string or if JSON decoding fails.
    """
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            pass
    return val
