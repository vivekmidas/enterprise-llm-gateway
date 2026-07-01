import json
from typing import Any


def property_entries_to_dict(value: Any) -> dict:
    if not value:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, str):
        try:
            return property_entries_to_dict(json.loads(value))
        except json.JSONDecodeError:
            return {}

    if isinstance(value, list):
        result = {}
        for item in value:
            entry = item
            if isinstance(item, str):
                try:
                    entry = json.loads(item)
                except json.JSONDecodeError:
                    continue

            if not isinstance(entry, dict):
                continue

            key = entry.get("key")
            if key:
                result[key] = entry.get("value", entry.get("default", ""))

        return result

    return {}


def safe_int(value: Any, default: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

