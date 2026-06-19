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
