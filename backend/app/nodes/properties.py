import copy
import json
from typing import Any


# ==============================================================================
# BLOCK COMMENT: CHOICE / TEXTAREA PROPERTY NORMALIZATION
# Reference: EPIC-NODE-PROPS-UI-001 / STORY-CHOICE-TEXTAREA-VALUES-001
# Description:
#     1. `normalize_choice_entry` preserves `options` on `choice`/`select`
#        entries. Legacy rows stored option lists as a comma-separated string
#        in `value` (e.g. "insert,update,delete,select"); these are lifted into
#        `options` so later value overrides cannot destroy the option list.
#     2. `property_entries_to_dict` falls back to `default` when `value` is
#        missing/None/"" so UI and runtime see the real default.
# ==============================================================================
CHOICE_TYPES = ("choice", "select")


def _split_options(raw: Any) -> list:
    if isinstance(raw, list):
        return [str(o).strip() for o in raw if str(o).strip()]
    if isinstance(raw, str) and raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return []


def normalize_choice_entry(entry: dict) -> dict:
    """Returns a copy of `entry` with `options` populated for choice/select fields."""
    if not isinstance(entry, dict):
        return entry
    entry = copy.deepcopy(entry)
    if str(entry.get("type", "")).lower() not in CHOICE_TYPES:
        return entry

    options = _split_options(entry.get("options") or entry.get("choices") or entry.get("allowed_values"))
    is_multi = bool(entry.get("multiple") or entry.get("multi_select"))
    if not options:
        # Legacy: options stored as comma-separated list in value/default
        for src in ("value", "default"):
            raw = entry.get(src)
            if isinstance(raw, str) and "," in raw and not is_multi:
                options = _split_options(raw)
                entry[src] = ""
                break
    if options:
        entry["options"] = options
    return entry


def resolve_entry_value(entry: dict) -> Any:
    """Resolves effective value for a schema entry (value -> default -> first option)."""
    entry = normalize_choice_entry(entry)
    val = entry.get("value")
    if val is None or val == "":
        val = entry.get("default", "")
    if (val is None or val == "") and str(entry.get("type", "")).lower() in CHOICE_TYPES:
        if not (entry.get("multiple") or entry.get("multi_select")):
            opts = entry.get("options") or []
            val = opts[0] if opts else ""
    return "" if val is None else val


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
                # EPIC-NODE-PROPS-UI-001: empty value falls back to default/first option
                result[key] = resolve_entry_value(entry)

        return result

    return {}


from app.utils.type_utils import safe_int, safe_float


