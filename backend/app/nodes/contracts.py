import functools
import json
import re
import threading
from typing import Any, Dict, List, Optional

import fastjsonschema
from app.core.types.common import NodeInput
import structlog

logger = structlog.get_logger(__name__)
logger.bind(file="contract")



def debug_log(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # logger.debug(
        #     "contracts_function_call",
        #     function=func.__name__,
        #     args=[type(arg).__name__ for arg in args],
        #     kwargs=list(kwargs.keys()),
        # )
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
    "ip_address": "string",
    "pdf": "file",
    "doc": "file",
    "docx": "file",
    "image": "file",
    "png": "file",
    "jpg": "file",
    "jpeg": "file",
    "file": "file",
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

def _check_mandatory_fields(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    if not isinstance(schema, dict):
        return errors
    if schema.get("type") == "object":
        if not isinstance(value, dict):
            return errors
        required = _required_fields(schema)
        for field in required:
            if field not in value:
                errors.append(f"{path}.{field} is mandatory")
        properties = schema.get("properties", {})
        for field, field_schema in properties.items():
            if field in value:
                errors.extend(_check_mandatory_fields(value[field], field_schema, f"{path}.{field}"))
    elif schema.get("type") == "array":
        if not isinstance(value, list):
            return errors
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_check_mandatory_fields(item, item_schema, f"{path}[{index}]"))
    return errors


# @debug_log
def validate_input_contract(
    contract: Dict[str, Any],
    inp: NodeInput,
    node_name: str = "node",
) -> List[str]:
    logger.info("starting_validate_input_contract", contract=contract.get("rules"), name=node_name,trace_id=inp.trace_id)
    schema = normalize_contract(contract)
    if not schema:
        return []

    body, errors = parse_input_data(inp)
    logger.info("end_alidate_input_contract", errors=errors, trace_id=inp.trace_id)
    if errors:
        return errors

    # Normalize body based on schema properties (wrapping or unwrapping as needed)
    if (
        schema.get("type") == "object"
        and isinstance(body, dict)
        and set(schema.get("properties", {}).keys()) == {"data"}
        and "data" not in body
    ):
        body = {"data": body}
    elif (
        schema.get("type") == "object"
        and isinstance(body, dict)
        and set(schema.get("properties", {}).keys()) == {"input_data"}
        and "input_data" not in body
    ):
        body = {"input_data": body}

    if (
        schema.get("type") == "object"
        and isinstance(body, dict)
        and "data" in body
        and isinstance(body["data"], dict)
        and "data" not in schema.get("properties", {})
    ):
        body = {**body["data"], **{k: v for k, v in body.items() if k != "data"}}

    return _validate_value(body, schema, "$")

#@debug_log
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


# @debug_log
def _schema_from_flat_rules(contract: Dict[str, Any]) -> Dict[str, Any]:
    root = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": contract.get("additional_fields", contract.get("additionalProperties", True)),
    }

    rules = [rule for rule in contract.get("rules", []) if isinstance(rule, dict)]
    for rule in sorted(rules, key=lambda item: len(str(item.get("field_name", item.get("name", ""))).split("."))):
        field_name = str(rule.get("field_name", rule.get("name", ""))).strip()
        if not field_name:
            continue
        field_schema = _schema_from_flat_rule(rule)
        _insert_path_rule(root, field_name.split("."), field_schema, _as_bool(rule.get("required", False)))

    return root


# @debug_log
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
        "stateable",
        "state_required",
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


# @debug_log
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


# @debug_log
def _merge_field_schema(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return incoming

    merged = {**existing, **incoming}
    if existing.get("properties") or incoming.get("properties"):
        merged["properties"] = {**existing.get("properties", {}), **incoming.get("properties", {})}
    if existing.get("required") or incoming.get("required"):
        merged["required"] = list(dict.fromkeys(existing.get("required", []) + incoming.get("required", [])))
    return merged


#@debug_log
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


# @debug_log
def _format_from_type(field_type: Any) -> Optional[str]:
    normalized = str(field_type or "").lower()
    if normalized == "phone_number":
        return "phone"
    if normalized in {"email", "password", "phone", "credit_card", "ip_address", "pdf", "doc", "docx", "image", "file"}:
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


_validator_cache = {}
_cache_lock = threading.Lock()

# Define the custom format checkers for fastjsonschema
def _is_email(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val))

def _is_phone(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^\+?[0-9][0-9 .()-]{6,20}$", val))

def _is_credit_card(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^[0-9][0-9 -]{11,22}[0-9]$", val))

def _is_url(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", val))

def _is_uuid(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$", val))

def _is_date(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", val))

def _is_datetime(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val))

def _is_ip_address(val):
    if not isinstance(val, str):
        return True
    return bool(re.match(r"^((25[0-5]|2[0-4]\d|1?\d?\d)(\.|$)){4}$", val))

# File formats: pdf, doc, docx, image, file
def _is_pdf(val):
    errors = _validate_file_constraints(val, {"format": "pdf"}, "")
    return len(errors) == 0

def _is_doc(val):
    errors = _validate_file_constraints(val, {"format": "doc"}, "")
    return len(errors) == 0

def _is_docx(val):
    errors = _validate_file_constraints(val, {"format": "docx"}, "")
    return len(errors) == 0

def _is_image(val):
    errors = _validate_file_constraints(val, {"format": "image"}, "")
    return len(errors) == 0

def _is_file(val):
    errors = _validate_file_constraints(val, {"format": "file"}, "")
    return len(errors) == 0

CUSTOM_FORMATS = {
    "email": _is_email,
    "phone": _is_phone,
    "credit_card": _is_credit_card,
    "url": _is_url,
    "uuid": _is_uuid,
    "date": _is_date,
    "datetime": _is_datetime,
    "ip_address": _is_ip_address,
    "pdf": _is_pdf,
    "doc": _is_doc,
    "docx": _is_docx,
    "image": _is_image,
    "file": _is_file,
}

def clean_json_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [clean_json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    cleaned = {}
    for k, v in schema.items():
        if k == "required":
            if isinstance(v, list):
                cleaned[k] = [str(x) for x in v]
            continue
        elif k == "type":
            if v == "file":
                cleaned[k] = ["string", "object"]
            elif v == "json":
                cleaned[k] = ["string", "number", "integer", "boolean", "array", "object", "null"]
            else:
                cleaned[k] = clean_json_schema(v)
        elif k in {"properties", "items"}:
            cleaned[k] = clean_json_schema(v)
        elif k in {"nullable"}:
            pass
        elif k in {"mandatory", "stateable", "state_required", "redact"}:
            pass
        else:
            cleaned[k] = clean_json_schema(v)

    if schema.get("nullable") is True and "type" in cleaned:
        t = cleaned["type"]
        if isinstance(t, str):
            if t != "null":
                cleaned["type"] = [t, "null"]
        elif isinstance(t, list):
            if "null" not in t:
                cleaned["type"] = t + ["null"]

    return cleaned

def get_validator(schema: dict):
    # Serialize schema to a stable key
    cleaned_schema = clean_json_schema(schema)
    schema_key = json.dumps(cleaned_schema, sort_keys=True)
    with _cache_lock:
        if schema_key not in _validator_cache:
            try:
                _validator_cache[schema_key] = fastjsonschema.compile(cleaned_schema, formats=CUSTOM_FORMATS)
            except Exception as e:
                logger.error("fastjsonschema_compile_failed", schema=schema, cleaned_schema=cleaned_schema, error=str(e))
                _validator_cache[schema_key] = fastjsonschema.compile(cleaned_schema)
        return _validator_cache[schema_key]

def translate_error(e: fastjsonschema.JsonSchemaValueException, path: str) -> List[str]:
    rule = e.rule
    msg = e.message
    
    # Path extraction: e.name is the variable name inside the compiled code, e.g. 'data.user_id' or 'data' or 'data[0]'
    clean_path = e.name
    if clean_path.startswith("data."):
        clean_path = "$." + clean_path[5:]
    elif clean_path == "data":
        clean_path = "$"
    elif clean_path.startswith("data["):
        clean_path = "$" + clean_path[4:]
    else:
        clean_path = path

    # If the clean_path is relative to the sub-validator's root ($), resolve to absolute path using parent path
    if clean_path.startswith("$") and path != "$":
        if clean_path == "$":
            clean_path = path
        elif clean_path.startswith("$."):
            clean_path = path + clean_path[1:]
        elif clean_path.startswith("$["):
            clean_path = path + clean_path[1:]

    # If the clean_path does not start with $, but we have a custom path, use the custom path
    if not clean_path.startswith("$"):
        if path.startswith("$"):
            clean_path = path
        else:
            clean_path = f"$.{clean_path}" if clean_path else "$"

    if rule == 'required':
        # E.g. "data.customer must contain ['id'] properties"
        import re
        match = re.search(r"must contain \['(.*)'\] properties", msg)
        if match:
            missing_field = match.group(1)
            if clean_path == "$":
                return [f"$.{missing_field} is mandatory"]
            else:
                return [f"{clean_path}.{missing_field} is mandatory"]
        return [f"{clean_path} is mandatory"]

    if rule == 'type':
        # E.g. "data.message must be string" -> "$.message expected string, got int"
        expected = e.rule_definition
        if isinstance(expected, list):
            expected_str = " or ".join(expected)
        else:
            expected_str = str(expected)
        
        got_type = type(e.value).__name__
        if got_type == "dict":
            got_type = "object"
        elif got_type == "list":
            got_type = "array"
        elif got_type == "bool":
            got_type = "bool"
        return [f"{clean_path} expected {expected_str}, got {got_type}"]

    if rule == 'minLength':
        return [f"{clean_path} length must be at least {e.rule_definition}"]

    if rule == 'maxLength':
        return [f"{clean_path} length must be at most {e.rule_definition}"]

    if rule == 'minimum':
        return [f"{clean_path} must be greater than or equal to {e.rule_definition}"]

    if rule == 'maximum':
        return [f"{clean_path} must be less than or equal to {e.rule_definition}"]

    if rule == 'format':
        fmt = e.rule_definition
        if fmt == "phone":
            return [f"{clean_path} must be a valid phone"]
        elif fmt == "credit_card":
            return [f"{clean_path} must be a valid credit_card"]
        elif fmt == "email":
            return [f"{clean_path} must be a valid email"]
        return [f"{clean_path} must be a valid {fmt}"]

    if rule == 'pattern':
        return [f"{clean_path} must match pattern {e.rule_definition}"]

    friendly_msg = msg
    if friendly_msg.startswith("data."):
        friendly_msg = "$." + friendly_msg[5:]
    elif friendly_msg.startswith("data "):
        friendly_msg = "$ " + friendly_msg[5:]
    return [friendly_msg]

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

def _has_custom_constraints(schema: Dict[str, Any]) -> bool:
    if not isinstance(schema, dict):
        return False
    fmt = schema.get("format")
    if schema.get("type") == "file" or (isinstance(fmt, str) and fmt.lower() in {"pdf", "doc", "docx", "image", "file", "password"}):
        return True
    if schema.get("type") == "object" and "properties" in schema:
        return any(_has_custom_constraints(p) for p in schema["properties"].values())
    if schema.get("type") == "array" and "items" in schema:
        return _has_custom_constraints(schema["items"])
    return False

@debug_log
def _validate_value(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    if not isinstance(schema, dict) or not schema:
        return []

    # File constraints check must run first as fastjsonschema skips format check on objects
    field_format = schema.get("format")
    is_file_type = schema.get("type") == "file" or (isinstance(field_format, str) and field_format.lower() in {"pdf", "doc", "docx", "image", "file"})
    if is_file_type:
        file_errors = _validate_file_constraints(value, schema, path)
        if file_errors:
            return file_errors

    # Run top-level compiled validator
    validator_failed = False
    validation_exc = None
    try:
        validator = get_validator(schema)
        validator(value)
    except fastjsonschema.JsonSchemaValueException as ex:
        validator_failed = True
        validation_exc = ex

    if not validator_failed and not _has_custom_constraints(schema):
        return []

    errors = []
    
    # 1. Custom password validation check if applicable
    if isinstance(value, str) and schema.get("type") == "string" and schema.get("format") == "password":
        errors.extend(_validate_password(value, schema, path))
        if errors:
            return errors

    # 3. Recurse properties if it is an object
    if schema.get("type") == "object" and isinstance(value, dict):
        # Check required
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                errors.append(f"{path}.{field} is mandatory")
        
        # Check properties
        properties = schema.get("properties", {})
        for field, field_schema in properties.items():
            if field in value:
                errors.extend(_validate_value(value[field], field_schema, f"{path}.{field}"))
        
        # Check additionalProperties
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                errors.append(f"{path} contains unsupported field(s): {', '.join(unknown)}")

    # 4. Recurse array items if it is an array
    elif schema.get("type") == "array" and isinstance(value, list):
        # Check minItems/maxItems
        if schema.get("minItems") is not None and len(value) < schema["minItems"]:
            errors.append(f"{path} must contain at least {schema['minItems']} item(s)")
        if schema.get("maxItems") is not None and len(value) > schema["maxItems"]:
            errors.append(f"{path} must contain at most {schema['maxItems']} item(s)")
        
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_validate_value(item, item_schema, f"{path}[{index}]"))

    # If it is a leaf failure or we didn't collect any nested errors, translate the error at this path
    if not errors and validator_failed and validation_exc:
        errors.extend(translate_error(validation_exc, path))
        
    return errors

@debug_log
def _normalize_type(value: Any) -> Any:
    if isinstance(value, list):
        return _normalize_type(value[0]) if value else ["string", "number", "integer", "boolean", "array", "object", "null"]
    normalized = str(value or "json").lower()
    resolved = TYPE_ALIASES.get(normalized, normalized)
    if resolved == "file":
        return ["string", "object"]
    if resolved == "json":
        return ["string", "number", "integer", "boolean", "array", "object", "null"]
    return resolved


@debug_log
def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


@debug_log
def _validate_file_constraints(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    errors = []
    field_format = str(schema.get("format") or "file").lower()

    # Extract extension or mime-type for validation
    ext = ""
    mime = ""

    if isinstance(value, str):
        # Could be path, url, or base64 data url
        if value.startswith("data:"):
            # e.g., data:application/pdf;base64,...
            match = re.match(r"^data:([^;]+);", value)
            if match:
                mime = match.group(1).lower()
        else:
            # simple path or url, check extension
            match = re.search(r"\.([a-zA-Z0-9]+)(?:[?#]|$)", value)
            if match:
                ext = match.group(1).lower()
    elif isinstance(value, dict):
        mime = str(value.get("mime_type") or value.get("mimeType") or value.get("content_type") or "").lower()
        file_name = str(value.get("file_name") or value.get("fileName") or value.get("name") or "").lower()
        if file_name:
            match = re.search(r"\.([a-zA-Z0-9]+)$", file_name)
            if match:
                ext = match.group(1)
        # fallback to checking file path/url inside the dictionary
        path_or_url = str(value.get("file_path") or value.get("filePath") or value.get("url") or "").lower()
        if path_or_url and not ext:
            match = re.search(r"\.([a-zA-Z0-9]+)(?:[?#]|$)", path_or_url)
            if match:
                ext = match.group(1)

    if field_format == "pdf":
        if ext and ext != "pdf":
            errors.append(f"{path} must be a PDF file (.pdf)")
        if mime and mime != "application/pdf":
            errors.append(f"{path} must be application/pdf")

    elif field_format in {"doc", "docx"}:
        if ext and ext not in {"doc", "docx"}:
            errors.append(f"{path} must be a Word document (.doc, .docx)")
        if mime and mime not in {"application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
            errors.append(f"{path} must be a Word document mime-type")

    elif field_format == "image":
        if ext and ext not in {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}:
            errors.append(f"{path} must be an image file (.png, .jpg, .jpeg, etc.)")
        if mime and not mime.startswith("image/"):
            errors.append(f"{path} must be an image mime-type (image/*)")

    return errors


@debug_log
def validate_output_contract(
    contract: Dict[str, Any],
    output: Any,  # NodeOutput or dict or str
    node_name: str = "node",
    context_nodes: Optional[Dict[str, Any]] = None
) -> List[str]:
    logger.info("starting validate_output_contract", contract=contract, name=node_name)
    schema = normalize_contract(contract)
    if not schema:
        return []

    from app.core.types.common import NodeOutput
    if isinstance(output, NodeOutput):
        body_str = output.data
    else:
        body_str = output

    body = body_str
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass

    # Build render context from the actual output body.
    render_context = {
        "data": body,
        **(body if isinstance(body, dict) else {}),
        "nodes": context_nodes or {},
    }

    resolved_body = resolve_jinja_templates_in_data(body, render_context)
    body = resolved_body

    # Update output data representation
    if isinstance(output, NodeOutput):
        if isinstance(resolved_body, (dict, list)):
            output.data = json.dumps(resolved_body)
        else:
            output.data = str(resolved_body)
    elif isinstance(output, dict):
        output.clear()
        if isinstance(resolved_body, dict):
            output.update(resolved_body)

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


def _resolve_single_expression(expr: str, context: Dict[str, Any]) -> Any:
    expr = expr.strip()
    lookup_expr = _normalize_lookup_expression(expr)

    # Support root[].field or similar path extraction
    if '[]' in lookup_expr:
        resolved = _extract_list_values(lookup_expr, context)
        if resolved is not None:
            return resolved

    # Try to resolve directly via dotted path lookup first
    if '.' in lookup_expr or lookup_expr in context:
        if not any(c in lookup_expr for c in ['"', "'", '(', ')']):
            resolved = _resolve_dotted_path(lookup_expr, context)
            if resolved is not None:
                return resolved

    # Otherwise, fall back to standard Jinja NativeTemplate render
    try:
        try:
            from jinja2.nativetypes import NativeTemplate
        except ImportError:
            from jinja2 import Template as NativeTemplate
        from jinja2 import Undefined

        tpl = NativeTemplate(f"{{{{ {expr} }}}}")
        rendered = tpl.render(**context)
        if isinstance(rendered, Undefined):
            return None
        return rendered
    except Exception:
        return None


def _normalize_lookup_expression(expr: str) -> str:
    stripped = expr.strip()
    if len(stripped) < 2 or stripped[0] != stripped[-1] or stripped[0] not in {"'", '"'}:
        return stripped

    unquoted = stripped[1:-1].strip()
    if re.match(r"^[A-Za-z_]\w*(?:\[\])?(?:\.[A-Za-z_]\w*(?:\[\])?)*$", unquoted):
        return unquoted
    return stripped


def _resolve_dotted_path(dotted_path: str, obj: Any) -> Any:
    parts = [p.strip() for p in dotted_path.split('.') if p.strip()]
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def _extract_list_values(expr: str, context: Dict[str, Any]) -> Optional[List[Any]]:
    path = expr.strip().strip("'\"")
    if '[]' not in path:
        return None

    left_part, right_part = path.split('[]', 1)
    left_part = left_part.strip()
    right_part = right_part.strip()

    if right_part.startswith('.'):
        field_name = right_part[1:]
    else:
        field_name = right_part

    target_list = None
    if left_part:
        target_list = _resolve_dotted_path(left_part, context)
        if target_list is None:
            for candidate in ["input_data", "inputdata", "data", "output"]:
                cand_ctx = context.get(candidate)
                if cand_ctx:
                    target_list = _resolve_dotted_path(left_part, cand_ctx)
                    if target_list is not None:
                        break

    if target_list is None or not isinstance(target_list, list):
        for candidate in ["input_data", "inputdata", "data", "output"]:
            cand_ctx = context.get(candidate)
            if isinstance(cand_ctx, list):
                target_list = cand_ctx
                break
            elif isinstance(cand_ctx, dict):
                if left_part and left_part in cand_ctx and isinstance(cand_ctx[left_part], list):
                    target_list = cand_ctx[left_part]
                    break
                elif 'data' in cand_ctx and isinstance(cand_ctx['data'], list):
                    target_list = cand_ctx['data']
                    break
                elif 'root' in cand_ctx and isinstance(cand_ctx['root'], list):
                    target_list = cand_ctx['root']
                    break

    if target_list is None or not isinstance(target_list, list):
        if isinstance(context, list):
            target_list = context
        elif isinstance(context, dict):
            for v in context.values():
                if isinstance(v, list):
                    target_list = v
                    break

    if not isinstance(target_list, list):
        return None

    result = []
    for item in target_list:
        if isinstance(item, dict):
            if field_name:
                val = _resolve_dotted_path(field_name, item)
                result.append(val)
            else:
                result.append(item)
        else:
            result.append(item)
    return result


def resolve_jinja_templates_in_data(template: Any, render_context: Dict[str, Any]) -> Any:
    if isinstance(template, dict):
        return {k: resolve_jinja_templates_in_data(v, render_context) for k, v in template.items()}
    elif isinstance(template, list):
        return [resolve_jinja_templates_in_data(i, render_context) for i in template]
    elif isinstance(template, str) and "{{" in template and "}}" in template:
        match = re.match(r"^\{\{\s*(.*?)\s*\}\}$", template.strip())
        if match:
            expr = match.group(1)
            resolved = _resolve_single_expression(expr, render_context)
            if resolved is not None:
                return resolved
            return template

        pattern = re.compile(r"\{\{\s*(.*?)\s*\}\}")
        def replace_match(m):
            expr = m.group(1)
            resolved = _resolve_single_expression(expr, render_context)
            if resolved is not None:
                if isinstance(resolved, (list, dict)):
                    return json.dumps(resolved)
                return str(resolved)
            return m.group(0)
        try:
            return pattern.sub(replace_match, template)
        except Exception:
            return template
    return template


def contract_from_expected_output(expected_output: Any) -> Optional[Dict[str, Any]]:
    """
    Parses the expected_output configuration and generates a dynamic contract schema definition.

    Args:
        expected_output: The expected output configuration (JSON string or dict).

    Returns:
        A dictionary representing the output contract schema with version and rules, or None.
    """
    if not expected_output:
        return None

    parsed = None
    if isinstance(expected_output, str):
        try:
            parsed = json.loads(expected_output)
        except Exception:
            return None
    else:
        parsed = expected_output

    if not isinstance(parsed, dict):
        return None

    rules = []
    for key, val in parsed.items():
        field_type = "string"
        if isinstance(val, bool):
            field_type = "boolean"
        elif isinstance(val, int):
            field_type = "integer"
        elif isinstance(val, float):
            field_type = "number"
        elif isinstance(val, dict):
            field_type = "object"
        elif isinstance(val, list):
            field_type = "array"

        rules.append({
            "field_name": key,
            "field_type": field_type
        })

    return {
        "version": "1.0",
        "rules": rules
    }

