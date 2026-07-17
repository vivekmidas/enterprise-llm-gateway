
"""
json_sample_generator.py

Production-ready skeleton for generating sample JSON from a flat schema.

{
  "data": {
    "table_name": "<string>"
  },
  "columns": [
    "<string>"
  ],
  "values": [
    {}
  ],
  "values[]": {
    "date": null,
    "open": 0,
    "high": 0,
    "low": 0,
    "close": 0,
    "adjusted_close": 0,
    "volume": 0
  }
}
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {"string","integer","number","boolean","null","object","array","phone","credit-card","email","uuid","date","datetime"}

class SchemaValidationError(ValueError):
    """Raised when the supplied schema is invalid."""

_XTYPE = {
    "credit-card":"4111111111111111",
    "email":"user@example.com",
    "phone":"+1-555-123-4567",
    "uuid":"550e8400-e29b-41d4-a716-446655440000",
    "date":"2026-07-17",
    "datetime":"2026-07-17T00:00:00Z"
}

def _primitive(field_type: str) -> Any:
    return {
        "string": "<string>",
        "integer": 0,
        "number": 0,
        "boolean": True,
        "null": None
    }.get(field_type)

def _validate(schema: dict) -> None:
    if not isinstance(schema, dict):
        raise SchemaValidationError("Schema must be a dict")
    rules = schema.get("rules")
    if not isinstance(rules, list):
        raise SchemaValidationError("'rules' must be a list")
    seen = set()
    for i, r in enumerate(rules):
        if "field_name" not in r or "field_type" not in r:
            raise SchemaValidationError(f"Rule {i} missing field_name/field_type")
        if r["field_name"] in seen:
            raise SchemaValidationError(f"Duplicate field {r['field_name']}")
        seen.add(r["field_name"])
        if r["field_type"] not in SUPPORTED_TYPES:
            raise SchemaValidationError(f"Unsupported field_type {r['field_type']}")
        if r["field_type"] == "array" and "items" not in r:
            raise SchemaValidationError(f"Array '{r['field_name']}' requires items")

def _assign(root: dict, path: list[str], value: Any) -> None:
    cur = root
    for i, p in enumerate(path[:-1]):
        if p.endswith("[]"):
            array_key = p[:-2]
            if array_key not in cur or not isinstance(cur[array_key], list):
                cur[array_key] = []
            
            if not cur[array_key]:
                next_p = path[i + 1]
                if next_p.endswith("[]"):
                    cur[array_key].append([])
                else:
                    cur[array_key].append({})
            
            cur = cur[array_key][0]
        else:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
            
    last_p = path[-1]
    if last_p.endswith("[]"):
        array_key = last_p[:-2]
        if array_key not in cur or not isinstance(cur[array_key], list):
            cur[array_key] = []
        if not cur[array_key]:
            cur[array_key].append(value)
        else:
            if not (value in ({}, [], [{}]) and cur[array_key][0]):
                cur[array_key][0] = value
    else:
        if last_p in cur:
            if isinstance(cur[last_p], dict) and value == {}:
                pass
            elif isinstance(cur[last_p], list) and value in ([], [{}]):
                pass
            else:
                cur[last_p] = value
        else:
            cur[last_p] = value

def _gen_value(rule: dict) -> Any:
    if rule.get("redact"):
        return None
    if "const" in rule:
        return rule["const"]
    if "enum" in rule:
        return rule["enum"][0]
    if "default" in rule:
        return rule["default"]
    xt = rule.get("x-type")
    if xt:
        if xt in _XTYPE:
            return _XTYPE[xt]
        logger.warning("Unknown x-type '%s', falling back", xt)
    
    ft = rule.get("field_type")
    if ft in _XTYPE:
        return _XTYPE[ft]
        
    t = rule["field_type"]
    if t == "object":
        return {}
    if t == "array":
        items = rule["items"]
        fake = {"field_type": items["field_type"], "x-type": items.get("x-type")}
        if items["field_type"] == "object":
            return [{}]
        return [_gen_value(fake)]
    return _primitive(t)

def generate_sample_json(schema: dict, mode: str = "template") -> dict:
    """
    Generate sample JSON from flat schema.
    """
    logger.info("Generating sample JSON")
    _validate(schema)
    result = {}
    # create object shells first
    for r in schema["rules"]:
        if r["field_type"] == "object":
            _assign(result, r["field_name"].split("."), {})
    for r in schema["rules"]:
        if r["field_type"] == "object":
            continue
        _assign(result, r["field_name"].split("."), _gen_value(r))
    logger.info("Generation complete")
    return result

if __name__=="__main__":
    example={
      "version":"1.0",
      "rules":[
        {"field_name":"user.first_name","field_type":"string"},
        {"field_name":"user.last_name","field_type":"string"},
        {"field_name":"credit","field_type":"string","x-type":"credit-card"},
        {"field_name":"addresses","field_type":"array","items":{"field_type":"string"}}
      ]
    }
    import json
    print(json.dumps(generate_sample_json(example),indent=2))
