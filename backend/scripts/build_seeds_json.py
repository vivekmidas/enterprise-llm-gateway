#!/usr/bin/env python3
# ==============================================================================
# BLOCK COMMENT: SEEDS.JSON GENERATOR SCRIPT
# Script: backend/scripts/build_seeds_json.py
# Description:
#     Generates backend/data/seeds/seeds.json from individual exported seed files.
#     Run once to produce the master seed file; commit the result to version control.
#     Re-run only when you need to regenerate from scratch.
# Usage: python3 scripts/build_seeds_json.py
# ==============================================================================
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.utils.uuid_utils import generate_uuidv7

seeds_dir = backend_dir / "data" / "seeds"

# Load existing exported files
domains_raw = json.loads((seeds_dir / "domains.json").read_text())
presets_raw = json.loads((seeds_dir / "provider_presets.json").read_text())
modules_raw = json.loads((seeds_dir / "rbac_modules.json").read_text())
roles_raw   = json.loads((seeds_dir / "rbac_roles.json").read_text())

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert domain knowledge extractor.\n"
    "Extract structured field values accurately from the provided document content based on the target schema.\n"
    "Maintain precise names, dates, identifiers, amounts, and citations.\n"
    "If you find additional relevant domain knowledge that is not covered by the target schema, "
    "output it under the 'extra_fields' key.\n"
    "Return valid JSON only."
)

DEFAULT_USER_PROMPT = (
    "Document Filename: {filename}\n\n"
    "Target Schema Fields:\n{fields_summary}\n\n"
    "Target JSON Structure:\n{fields_json_schema}\n\n"
    "Document Content:\n{content}\n\n"
    "Extract all matching schema fields and any unmapped extra domain knowledge in valid JSON format matching:\n"
    '{{\n  "extracted_fields": {{ ... }},\n  "extra_fields": {{ ... }}\n}}'
)

# =============================================================================
# 1. ekp_domains table
# =============================================================================
ekp_domains_entry = {
    "table": "ekp_domains",
    "match_field": "id",
    "preserve_on_update": ["schema_definition"],
    "schema": {
        "id":               {"type": "string",  "length": 64,  "pk": True,  "nullable": False},
        "name":             {"type": "string",  "length": 128, "nullable": False},
        "version":          {"type": "string",  "length": 32,  "nullable": False, "default": "1.0"},
        "schema_definition":{"type": "json",    "nullable": False},
        "is_active":        {"type": "boolean", "nullable": True, "default": True, "index": True},
        "created_at":       {"type": "datetime","auto_now_add": True}
    },
    "rows": []
}

for dom in domains_raw:
    ekp_domains_entry["rows"].append({
        "id":               dom["domain_key"],
        "name":             dom["name"],
        "version":          "1.0",
        "schema_definition": dom["schema_data"],
        "is_active":        True,
    })

# =============================================================================
# 2. domain_schemas table
# =============================================================================
domain_schemas_entry = {
    "table": "domain_schemas",
    "match_field": "domain_key",  # natural key: one system schema per domain_key where customer_id IS NULL
    "preserve_on_update": ["system_prompt", "user_prompt", "schema_json"],
    "schema": {
        "id":           {"type": "uuid",   "pk": True,  "nullable": False},
        "name":         {"type": "string", "length": 255, "nullable": False, "index": True},
        "description":  {"type": "text",   "nullable": True},
        "domain_key":   {"type": "string", "length": 100, "nullable": False, "index": True},
        "scope":        {"type": "string", "length": 50,  "nullable": True,  "index": True, "default": "TENANT"},
        "customer_id":  {"type": "uuid",   "nullable": True,  "index": True, "fk": "customers.id"},
        "schema_json":  {"type": "json",   "nullable": True},
        "system_prompt":{"type": "text",   "nullable": True},
        "user_prompt":  {"type": "text",   "nullable": True},
        "created_by":   {"type": "uuid",   "nullable": True, "fk": "users.id"},
        "created_at":   {"type": "string", "length": 100, "auto_now_add": True},
        "updated_at":   {"type": "string", "length": 100, "auto_now_add": True, "auto_now": True}
    },
    "rows": []
}

for dom in domains_raw:
    domain_schemas_entry["rows"].append({
        "id":            dom["id"],
        "name":          dom["name"],
        "description":   dom.get("description", ""),
        "domain_key":    dom["domain_key"],
        "scope":         dom.get("scope", "SYSTEM"),
        "customer_id":   None,
        "schema_json":   dom["schema_data"],
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt":   DEFAULT_USER_PROMPT,
        "created_by":    None,
    })

# =============================================================================
# 3. provider_presets table
# =============================================================================
valid_preset_cols = {
    "id", "provider_key", "name", "display_name", "description", "base_url",
    "model_types", "chat_models", "default_chat_model", "search_endpoint",
    "embedding_models", "default_embedding_model", "default_embedding_dimension",
    "embedding_endpoint", "rerank_models", "default_rerank_model", "rerank_endpoint",
    "default_temperature", "default_max_tokens", "api_key_header",
    "capability_configs", "extra_config", "is_active"
}

provider_presets_entry = {
    "table": "provider_presets",
    "match_field": "provider_key",  # natural key: stable, human-readable identifier
    "preserve_on_update": [
        "base_url", "api_key_header", "model_types", "chat_models",
        "embedding_models", "rerank_models", "is_active"
    ],
    "schema": {
        "id":                          {"type": "uuid",    "pk": True,  "nullable": False},
        "provider_key":                {"type": "string",  "length": 100, "nullable": False, "unique": True, "index": True},
        "name":                        {"type": "string",  "length": 255, "nullable": False},
        "display_name":                {"type": "string",  "length": 255, "nullable": True},
        "description":                 {"type": "string",  "length": 1000,"nullable": True},
        "base_url":                    {"type": "string",  "length": 500, "nullable": False},
        "model_types":                 {"type": "json",    "nullable": True},
        "chat_models":                 {"type": "json",    "nullable": True},
        "default_chat_model":          {"type": "string",  "length": 255, "nullable": True},
        "search_endpoint":             {"type": "string",  "length": 500, "nullable": True},
        "embedding_models":            {"type": "json",    "nullable": True},
        "default_embedding_model":     {"type": "string",  "length": 255, "nullable": True},
        "default_embedding_dimension": {"type": "integer", "nullable": True},
        "embedding_endpoint":          {"type": "string",  "length": 500, "nullable": True},
        "rerank_models":               {"type": "json",    "nullable": True},
        "default_rerank_model":        {"type": "string",  "length": 255, "nullable": True},
        "rerank_endpoint":             {"type": "string",  "length": 500, "nullable": True},
        "default_temperature":         {"type": "float",   "nullable": True, "default": 0.7},
        "default_max_tokens":          {"type": "integer", "nullable": True, "default": 1024},
        "api_key_header":              {"type": "string",  "length": 100, "nullable": True},
        "capability_configs":          {"type": "json",    "nullable": True},
        "extra_config":                {"type": "json",    "nullable": True},
        "is_active":                   {"type": "boolean", "nullable": True, "default": True, "index": True},
        "created_at":                  {"type": "string",  "length": 100, "auto_now_add": True},
        "updated_at":                  {"type": "string",  "length": 100, "auto_now_add": True, "auto_now": True}
    },
    "rows": [{k: v for k, v in p.items() if k in valid_preset_cols} for p in presets_raw]
}

# =============================================================================
# 4. modules table
# =============================================================================
modules_entry = {
    "table": "modules",
    "match_field": "id",
    "preserve_on_update": [],
    "schema": {
        "id":             {"type": "string", "length": 50,  "pk": True,  "nullable": False},
        "customer_id":    {"type": "uuid",   "nullable": True,  "index": True, "fk": "customers.id", "on_delete": "CASCADE"},
        "module":         {"type": "string", "length": 50,  "nullable": False, "index": True},
        "submodule":      {"type": "string", "length": 50,  "nullable": True,  "index": True},
        "label":          {"type": "string", "length": 150, "nullable": False},
        "description":    {"type": "text",   "nullable": True},
        "route_patterns": {"type": "json",   "nullable": False},
        "icon":           {"type": "string", "length": 50,  "nullable": True},
        "display_order":  {"type": "integer","nullable": True, "default": 0},
        "created_at":     {"type": "string", "length": 100, "auto_now_add": True},
        "updated_at":     {"type": "string", "length": 100, "auto_now_add": True, "auto_now": True}
    },
    "rows": []
}

for mod in modules_raw:
    modules_entry["rows"].append({
        "id":             mod["id"],
        "customer_id":    None,
        "module":         mod["module"],
        "submodule":      mod.get("submodule"),
        "label":          mod["label"],
        "description":    mod.get("description"),
        "route_patterns": mod.get("route_patterns", []),
        "icon":           mod.get("icon"),
        "display_order":  mod.get("display_order", 0),
    })

# =============================================================================
# 5. permissions table
# =============================================================================
permissions_entry = {
    "table": "permissions",
    "match_field": "id",
    "preserve_on_update": [],
    "schema": {
        "id":            {"type": "string",  "length": 100, "pk": True,  "nullable": False},
        "module_id":     {"type": "string",  "length": 50,  "nullable": True,  "index": True, "fk": "modules.id", "on_delete": "CASCADE"},
        "module":        {"type": "string",  "length": 50,  "nullable": False, "index": True},
        "submodule":     {"type": "string",  "length": 50,  "nullable": True,  "index": True},
        "action":        {"type": "string",  "length": 50,  "nullable": True,  "index": True},
        "is_route_guard":{"type": "boolean", "nullable": True, "default": False},
        "target_layer":  {"type": "string",  "length": 20,  "nullable": True, "default": "both"},
        "api_path":      {"type": "string",  "length": 255, "nullable": True},
        "http_methods":  {"type": "json",    "nullable": True},
        "label":         {"type": "string",  "length": 150, "nullable": False},
        "description":   {"type": "text",    "nullable": True}
    },
    "rows": []
}

# Wildcards first
WILDCARDS = [
    {"id": "*:*:*",         "module": "admin",     "submodule": "all", "action": "*", "label": "Global System Super Admin",    "description": "Unrestricted system super admin access",   "is_route_guard": True},
    {"id": "admin:*:*",     "module": "admin",     "submodule": "all", "action": "*", "label": "Admin Domain Full Access",     "description": "Full access to all admin submodules",      "is_route_guard": True},
    {"id": "legal:*:*",     "module": "legal",     "submodule": "all", "action": "*", "label": "Legal Domain Full Access",     "description": "Full access to all legal submodules",      "is_route_guard": True},
    {"id": "kb:*:*",        "module": "knowledge", "submodule": "all", "action": "*", "label": "Knowledge Domain Full Access", "description": "Full access to knowledge submodules",      "is_route_guard": True},
    {"id": "workflow:*:*",  "module": "workflows", "submodule": "all", "action": "*", "label": "Workflows Domain Full Access", "description": "Full access to workflow submodules",       "is_route_guard": True},
    {"id": "node:*:*",      "module": "nodes",     "submodule": "all", "action": "*", "label": "Nodes Domain Full Access",     "description": "Full access to node submodules",           "is_route_guard": True},
]

for w in WILDCARDS:
    permissions_entry["rows"].append({
        "id": w["id"], "module_id": None, "module": w["module"], "submodule": w["submodule"],
        "action": w["action"], "is_route_guard": w["is_route_guard"],
        "target_layer": "both", "api_path": None, "http_methods": None,
        "label": w["label"], "description": w["description"],
    })

for mod in modules_raw:
    for act in mod.get("actions", []):
        perm_id = f"{mod['module']}:{mod.get('submodule', 'all')}:{act['action']}"
        permissions_entry["rows"].append({
            "id":             perm_id,
            "module_id":      mod["id"],
            "module":         mod["module"],
            "submodule":      mod.get("submodule"),
            "action":         act["action"],
            "is_route_guard": act.get("is_route_guard", False),
            "target_layer":   "both",
            "api_path":       act.get("api_path"),
            "http_methods":   act.get("http_methods"),
            "label":          act["label"],
            "description":    act.get("description"),
        })

# =============================================================================
# 6. roles table
# =============================================================================
roles_entry = {
    "table": "roles",
    "match_field": ["role_type", "customer_id"],  # composite natural key: system presets have customer_id = NULL
    "preserve_on_update": ["role_name", "description"],
    "schema": {
        "id":              {"type": "uuid",    "pk": True,  "nullable": False},
        "customer_id":     {"type": "uuid",    "nullable": True,  "index": True, "fk": "customers.id", "on_delete": "CASCADE"},
        "role_name":       {"type": "string",  "length": 100, "nullable": False},
        "role_type":       {"type": "string",  "length": 50,  "nullable": False},
        "description":     {"type": "text",    "nullable": True},
        "is_system_preset":{"type": "boolean", "nullable": True, "default": False},
        "created_at":      {"type": "string",  "length": 100, "auto_now_add": True},
        "updated_at":      {"type": "string",  "length": 100, "auto_now_add": True, "auto_now": True}
    },
    "rows": []
}

for role in roles_raw:
    roles_entry["rows"].append({
        "id":               role["id"],
        "customer_id":      None,
        "role_name":        role["role_name"],
        "role_type":        role["role_type"],
        "description":      role.get("description", ""),
        "is_system_preset": True,
    })

# =============================================================================
# 7. role_permissions table (join table — match on composite key)
# =============================================================================
role_perms_entry = {
    "table": "role_permissions",
    "match_field": ["role_id", "permission_id"],
    "preserve_on_update": [],
    "schema": {
        "id":            {"type": "uuid",   "pk": True,  "nullable": False},
        "role_id":       {"type": "uuid",   "nullable": False, "index": True, "fk": "roles.id",       "on_delete": "CASCADE"},
        "permission_id": {"type": "string", "length": 100, "nullable": False, "index": True, "fk": "permissions.id", "on_delete": "CASCADE"},
        "allowed_methods":{"type": "json",  "nullable": True}
    },
    "rows": []
}

for role in roles_raw:
    role_type = role["role_type"]
    for perm_id in role.get("permissions", []):
        role_perms_entry["rows"].append({
            "id":             generate_uuidv7(),
            # @ref resolves the actual DB role id at seed time by matching role_type
            "role_id":        f"@ref:roles:role_type={role_type}:id",
            "permission_id":  perm_id,
            "allowed_methods": None,
        })

# =============================================================================
# Assemble ordered seeds array (FK order matters)
# =============================================================================
seeds = [
    ekp_domains_entry,
    domain_schemas_entry,
    provider_presets_entry,
    modules_entry,
    permissions_entry,
    roles_entry,
    role_perms_entry,
]

output_path = seeds_dir / "seeds.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(seeds, f, indent=2, ensure_ascii=False)

print(f"seeds.json written → {output_path}")
for entry in seeds:
    print(f"  {entry['table']}: {len(entry['rows'])} rows")
