import functools
import json
import re
from typing import Any, Dict, List, Optional

from app.core.types.common import NodeInput
import structlog

logger = structlog.get_logger(__name__)


def debug_log(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(
            "contracts_function_call",
            function=func.__name__,
            args=[type(arg).__name__ for arg in args],
            kwargs=list(kwargs.keys()),
        )
        return func(*args, **kwargs)

    return wrapper


TYPE_ALIASES = {
    "str": "string",
    "text": "string",
    "textarea": "string",
    "float": "number",
    "double": "number",
    "int": "integer",
    "bool": "boolean",
    "dict": "object",
    "map": "object",
    "list": "array",
    "email": "string",
    "password": "string",
    "phone": "string",
    "phone_number": "string",
    "creditcard": "string",
    "credit_card": "string",
}

FORMAT_PATTERNS = {
    "email": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    "phone": r"^\+?[0-9][0-9 .()-]{6,20}$",
    "credit_card": r"^[0-9][0-9 -]{11,22}[0-9]$",
    "url": r"^https?://[^\s/$.?#].[^\s]*$",
    "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    "date": r"^\d{4}-\d{2}-\d{2}$",
    "datetime": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    "ip_address": r"^((25[0-5]|2[0-4]\d|1?\d?\d)(\.|$)){4}$",
}


@debug_log
def parse_input_data(inp: NodeInput) -> tuple[Any, List[str]]:
    logger.info("parse_input_data_started", trace_id=inp.trace_id, data_present=bool(inp.data))
    if not inp.data:
        return None, ["$.data is mandatory"]
    try:
        return json.loads(inp.data), []
    except (json.JSONDecodeError, TypeError):
        # Fall back to raw string
        return inp.data, []


@debug_log
def normalize_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(contract, dict) or not contract:
        return {}

    if isinstance(contract.get("rules"), list):
        return _schema_from_flat_rules(contract)

    raw = contract
    if isinstance(raw.get("properties"), dict) and isinstance(raw["properties"].get("rules"), dict):
        raw = raw["properties"]["rules"]
    elif isinstance(raw.get("rules"), dict):
        raw = raw["rules"]

    if raw.get("type") == "object" and isinstance(raw.get("properties"), dict):
        normalized = dict(raw)
        normalized["properties"] = {
            key: _normalize_field_rule(value) for key, value in raw.get("properties", {}).items()
        }
        normalized["required"] = _required_fields(normalized)
        return normalized

    properties = {
        key: _normalize_field_rule(value)
        for key, value in raw.items()
        if key not in {"type", "required", "mandatory", "additionalProperties"}
    }
    normalized = {
        "type": "object",
        "properties": properties,
        "additionalProperties": raw.get("additionalProperties", True),
    }
    normalized["required"] = _required_fields(raw, properties)
    return normalized

@debug_log
def validate_input_contract(contract: Dict[str, Any], inp: NodeInput, node_name: str = "node") -> List[str]:
    logger.info("starting validate_input_contract", contract=contract, input=inp, name=node_name)
    schema = normalize_contract(contract)
    if not schema:
        return []

    body, errors = parse_input_data(inp)
    logger.info("End validate_input_contract", errors=errors)
    if errors:
        return errors
    if (
        schema.get("type") == "object"
        and isinstance(body, dict)
        and set(schema.get("properties", {}).keys()) == {"data"}
        and "data" not in body
    ):
        body = {"data": body}

    if (
        schema.get("type") == "object"
        and isinstance(body, dict)
        and "data" in body
        and isinstance(body["data"], dict)
        and "data" not in schema.get("properties", {})
    ):
        body = {**body["data"], **{k: v for k, v in body.items() if k != "data"}}

    return _validate_value(body, schema, "$")


@debug_log
def _normalize_field_rule(rule: Any) -> Dict[str, Any]:
    if isinstance(rule, str):
        return {"type": _normalize_type(rule)}
    if not isinstance(rule, dict):
        return {"type": "json"}

    normalized = dict(rule)
    if "mandatory" in normalized and "required" not in normalized:
        normalized["required"] = normalized["mandatory"]

    if "type" in normalized:
        normalized["type"] = _normalize_type(normalized["type"])
    elif _looks_like_nested_properties(normalized):
        normalized["type"] = "object"
        normalized["properties"] = {
            key: _normalize_field_rule(value)
            for key, value in normalized.items()
            if key not in {"required", "mandatory", "values"}
        }
    elif "values" in normalized:
        normalized["type"] = "array" if isinstance(normalized.get("values"), list) else "json"

    if isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {
            key: _normalize_field_rule(value) for key, value in normalized["properties"].items()
        }
        normalized["required"] = _required_fields(normalized)

    if isinstance(normalized.get("items"), dict):
        normalized["items"] = _normalize_field_rule(normalized["items"])
    elif isinstance(normalized.get("items"), str):
        normalized["items"] = {"type": _normalize_type(normalized["items"])}

    _normalize_constraint_aliases(normalized)
    return normalized


@debug_log
def _schema_from_flat_rules(contract: Dict[str, Any]) -> Dict[str, Any]:
    root = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": contract.get("additional_fields", contract.get("additionalProperties", True)),
    }

    rules = [rule for rule in contract.get("rules", []) if isinstance(rule, dict)]
    for rule in sorted(rules, key=lambda item: len(str(item.get("field_name", "")).split("."))):
        field_name = str(rule.get("field_name", "")).strip()
        if not field_name:
            continue
        field_schema = _schema_from_flat_rule(rule)
        _insert_path_rule(root, field_name.split("."), field_schema, _as_bool(rule.get("required", False)))

    return root


@debug_log
def _schema_from_flat_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    field_type = rule.get("field_type", rule.get("type", "json"))
    schema = {"type": _normalize_type(field_type)}
    semantic_format = _format_from_type(field_type)
    if semantic_format:
        schema["format"] = semantic_format

    passthrough_keys = {
        "nullable",
        "description",
        "default",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "items",
        "redact",
        "require_uppercase",
        "require_lowercase",
        "require_number",
        "require_special",
    }
    for key in passthrough_keys:
        if key in rule:
            schema[key] = rule[key]

    if "allowed_values" in rule:
        schema["enum"] = rule["allowed_values"]
    if "enum" in rule:
        schema["enum"] = rule["enum"]
    if "min_length" in rule:
        schema["minLength"] = rule["min_length"]
    if "max_length" in rule:
        schema["maxLength"] = rule["max_length"]
    if "min_items" in rule:
        schema["minItems"] = rule["min_items"]
    if "max_items" in rule:
        schema["maxItems"] = rule["max_items"]
    if (
        "allow_negative" in rule
        and _as_bool(rule.get("allow_negative")) is False
        and schema["type"] in {"number", "integer"}
    ):
        schema.setdefault("minimum", 0)

    if schema.get("format") in {"phone_number", "creditcard"}:
        schema["format"] = "phone" if schema["format"] == "phone_number" else "credit_card"

    if isinstance(schema.get("items"), dict):
        schema["items"] = _schema_from_flat_rule(schema["items"])
    elif isinstance(schema.get("items"), str):
        schema["items"] = {"type": _normalize_type(schema["items"])}

    return schema


@debug_log
def _insert_path_rule(
    root: Dict[str, Any], path_parts: List[str], field_schema: Dict[str, Any], required: bool
) -> None:
    current = root
    for index, part in enumerate(path_parts):
        is_leaf = index == len(path_parts) - 1
        properties = current.setdefault("properties", {})

        if is_leaf:
            existing = properties.get(part, {})
            properties[part] = _merge_field_schema(existing, field_schema)
            if required and part not in current.setdefault("required", []):
                current["required"].append(part)
            continue

        child = properties.setdefault(part, {"type": "object", "properties": {}, "required": []})
        child["type"] = "object"
        child.setdefault("properties", {})
        child.setdefault("required", [])
        if required and part not in current.setdefault("required", []):
            current["required"].append(part)
        current = child


@debug_log
def _merge_field_schema(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return incoming

    merged = {**existing, **incoming}
    if existing.get("properties") or incoming.get("properties"):
        merged["properties"] = {**existing.get("properties", {}), **incoming.get("properties", {})}
    if existing.get("required") or incoming.get("required"):
        merged["required"] = list(dict.fromkeys(existing.get("required", []) + incoming.get("required", [])))
    return merged


@debug_log
def _normalize_constraint_aliases(schema: Dict[str, Any]) -> None:
    if "min_length" in schema and "minLength" not in schema:
        schema["minLength"] = schema["min_length"]
    if "max_length" in schema and "maxLength" not in schema:
        schema["maxLength"] = schema["max_length"]
    if "allowed_values" in schema and "enum" not in schema:
        schema["enum"] = schema["allowed_values"]
    if (
        "allow_negative" in schema
        and _as_bool(schema.get("allow_negative")) is False
        and schema.get("type") in {"number", "integer"}
    ):
        schema.setdefault("minimum", 0)


@debug_log
def _format_from_type(field_type: Any) -> Optional[str]:
    normalized = str(field_type or "").lower()
    if normalized == "phone_number":
        return "phone"
    if normalized in {"email", "password", "phone", "credit_card"}:
        return normalized
    if normalized == "creditcard":
        return "credit_card"
    return None


@debug_log
def _looks_like_nested_properties(rule: Dict[str, Any]) -> bool:
    ignored = {"required", "mandatory", "values", "description", "default", "nullable"}
    return any(isinstance(value, dict) for key, value in rule.items() if key not in ignored)


@debug_log
def _required_fields(schema: Dict[str, Any], properties: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    required = schema.get("required", schema.get("mandatory", []))
    if isinstance(required, str):
        required = [required]
    if not isinstance(required, list):
        required = []

    props = properties or schema.get("properties", {})
    for field, rules in props.items():
        if _as_bool(rules.get("required", rules.get("mandatory", False))) and field not in required:
            required.append(field)
    return required


@debug_log
def _validate_value(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    """Validate one value against a single field schema and return any violations."""

    errors: List[str] = []

    if value is None:
        if _as_bool(schema.get("nullable", False)) or schema.get("type") == "null":
            return errors
        return [f"{path} must not be null"]

    expected_type = _normalize_type(schema.get("type", "json"))
    if not _matches_type(value, expected_type):
        return [f"{path} expected {expected_type}, got {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {schema['enum']}")

    if expected_type in {"number", "integer"}:
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path} must be greater than or equal to {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path} must be less than or equal to {maximum}")

    if expected_type == "string":
        errors.extend(_validate_string_constraints(value, schema, path))
    elif expected_type == "array":
        errors.extend(_validate_array_constraints(value, schema, path))
    elif expected_type == "object":
        errors.extend(_validate_object_constraints(value, schema, path))
    elif expected_type == "json" and isinstance(value, str):
        try:
            json.loads(value)
        except json.JSONDecodeError:
            errors.append(f"{path} expected valid JSON string")

    return errors


@debug_log
def _validate_string_constraints(value: str, schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    if schema.get("minLength") is not None and len(value) < schema["minLength"]:
        errors.append(f"{path} length must be at least {schema['minLength']}")
    if schema.get("maxLength") is not None and len(value) > schema["maxLength"]:
        errors.append(f"{path} length must be at most {schema['maxLength']}")
    if schema.get("pattern") and not re.search(schema["pattern"], value):
        errors.append(f"{path} must match pattern {schema['pattern']}")
    field_format = schema.get("format")
    if field_format:
        errors.extend(_validate_format(value, str(field_format), schema, path))
    return errors


@debug_log
def _validate_format(value: str, field_format: str, schema: Dict[str, Any], path: str) -> List[str]:
    normalized_format = field_format.lower()
    if normalized_format in {"phone_number", "creditcard"}:
        normalized_format = "phone" if normalized_format == "phone_number" else "credit_card"

    pattern = FORMAT_PATTERNS.get(normalized_format)
    if pattern and not re.search(pattern, value):
        return [f"{path} must be a valid {normalized_format}"]

    if normalized_format == "password":
        return _validate_password(value, schema, path)

    return []


@debug_log
def _validate_password(value: str, schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    if _as_bool(schema.get("require_uppercase", False)) and not re.search(r"[A-Z]", value):
        errors.append(f"{path} must contain an uppercase letter")
    if _as_bool(schema.get("require_lowercase", False)) and not re.search(r"[a-z]", value):
        errors.append(f"{path} must contain a lowercase letter")
    if _as_bool(schema.get("require_number", False)) and not re.search(r"\d", value):
        errors.append(f"{path} must contain a number")
    if _as_bool(schema.get("require_special", False)) and not re.search(r"[^A-Za-z0-9]", value):
        errors.append(f"{path} must contain a special character")
    return errors


@debug_log
def _validate_array_constraints(value: List[Any], schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    if schema.get("minItems") is not None and len(value) < schema["minItems"]:
        errors.append(f"{path} must contain at least {schema['minItems']} item(s)")
    if schema.get("maxItems") is not None and len(value) > schema["maxItems"]:
        errors.append(f"{path} must contain at most {schema['maxItems']} item(s)")
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            errors.extend(_validate_value(item, item_schema, f"{path}[{index}]"))
    return errors


@debug_log
def _validate_object_constraints(value: Dict[str, Any], schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    properties = schema.get("properties", {})
    required = _required_fields(schema)

    for field in required:
        if field not in value:
            errors.append(f"{path}.{field} is mandatory")

    for field, field_schema in properties.items():
        if field in value:
            errors.extend(_validate_value(value[field], field_schema, f"{path}.{field}"))

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(value) - set(properties))
        if unknown:
            errors.append(f"{path} contains unsupported field(s): {', '.join(unknown)}")
    return errors


@debug_log
def _normalize_type(value: Any) -> str:
    if isinstance(value, list):
        return _normalize_type(value[0]) if value else "json"
    normalized = str(value or "json").lower()
    return TYPE_ALIASES.get(normalized, normalized)


@debug_log
def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "json":
        return isinstance(value, (dict, list, str, int, float, bool)) or value is None
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


@debug_log
def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)
