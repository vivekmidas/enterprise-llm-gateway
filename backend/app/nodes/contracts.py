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

@debug_log
def validate_input_contract(
    contract: Dict[str, Any],
    inp: NodeInput,
    node_name: str = "node",
    predecessor_output: Optional[Any] = None,
    workflow_input: Optional[Any] = None
) -> List[str]:
    logger.info("starting validate_input_contract", contract=contract.get("rules"), input=inp.data, name=node_name)
    schema = normalize_contract(contract)
    if not schema:
        return []

    body, errors = parse_input_data(inp)
    logger.info("End validate_input_contract", errors=errors)
    if errors:
        return errors

    # Parse predecessor_output and workflow_input if strings
    parsed_output = predecessor_output
    if isinstance(parsed_output, str):
        try:
            parsed_output = json.loads(parsed_output)
        except Exception:
            pass

    parsed_input = workflow_input
    if isinstance(parsed_input, str):
        try:
            parsed_input = json.loads(parsed_input)
        except Exception:
            pass

    render_context = {
        "output": parsed_output,
        "data": parsed_output,
        "inputdata": parsed_input,
        "input_data": parsed_input,
        "nodes": inp.context.get("nodes", {}) if (inp and getattr(inp, "context", None)) else {},
    }

    # Resolve templates in the body
    resolved_body = resolve_jinja_templates_in_data(body, render_context)
    body = resolved_body

    # Update inp.data to propagate resolved values
    if isinstance(resolved_body, (dict, list)):
        inp.data = json.dumps(resolved_body)
    else:
        inp.data = str(resolved_body)

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

    field_format = schema.get("format")
    if expected_type == "file" or field_format in {"pdf", "doc", "docx", "image", "file"}:
        errors.extend(_validate_file_constraints(value, schema, path))

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
    if expected_type == "file":
        return isinstance(value, (str, dict))
    return True


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
    predecessor_output: Optional[Any] = None,
    workflow_input: Optional[Any] = None,
    context_nodes: Optional[Dict[str, Any]] = None
) -> List[str]:
    logger.info("starting validate_output_contract", contract=contract, output=output, name=node_name)
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

    parsed_output = predecessor_output
    if isinstance(parsed_output, str):
        try:
            parsed_output = json.loads(parsed_output)
        except Exception:
            pass

    parsed_input = workflow_input
    if isinstance(parsed_input, str):
        try:
            parsed_input = json.loads(parsed_input)
        except Exception:
            pass

    render_context = {
        "output": parsed_output,
        "data": parsed_output,
        "inputdata": parsed_input,
        "input_data": parsed_input,
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
    
    # Support root[].field or similar path extraction
    if '[]' in expr:
        resolved = _extract_list_values(expr, context)
        if resolved is not None:
            return resolved
            
    # Try to resolve directly via dotted path lookup first
    if '.' in expr or expr in context:
        if not any(c in expr for c in ['"', "'", '(', ')']):
            resolved = _resolve_dotted_path(expr, context)
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


