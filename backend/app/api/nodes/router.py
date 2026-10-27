from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, or_, select, delete
import structlog
import json
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.db_models import CategoryDB, NodeDB, CustomerNodeDB
from app.nodes.properties import property_entries_to_dict
from app.workflows.store import propagate_node_defaults_to_workflows
from app.api.auth.dependencies import get_current_user, require_system_admin, dynamic_api_guard
from app.core.types.users import User
from app.utils.json_sample_generator import generate_sample_json
from app.utils.request_utils import extract_request_info

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


def _defaults_from_payload(node_data: dict) -> dict:
    return property_entries_to_dict(node_data.get("user_properties"))

def _nodes_with_categories_query():
    node_columns = [
        column
        for column in NodeDB.__table__.columns
        if column.name not in {"category_id", "category_color"}
    ]

    return (
        select(
            *node_columns,
            CategoryDB.id.label("category_id"),
            CategoryDB.color.label("category_color"),
        )
        .select_from(NodeDB)
        .outerjoin(CategoryDB, cast(CategoryDB.id, String) == NodeDB.category)
    )

async def _fetch_nodes(db: AsyncSession, statement):
    result = await db.execute(statement)
    rows = []
    for row in result.mappings().all():
        d = dict(row)
        raw_nt = str(d.get("node_type") or "NODE").strip().upper()
        d["node_type"] = "NODE" if raw_nt == "DEFAULT" or not raw_nt else raw_nt
        rows.append(d)
    return rows

async def _fetch_node(db: AsyncSession, statement):
    result = await db.execute(statement)
    row = result.mappings().one_or_none()
    if not row:
        return None
    d = dict(row)
    raw_nt = str(d.get("node_type") or "NODE").strip().upper()
    d["node_type"] = "NODE" if raw_nt == "DEFAULT" or not raw_nt else raw_nt
    return d


def _is_sensitive_property(key: str, prop_type: str = "") -> bool:
    """
    ===========================================================================
    BLOCK COMMENT: PROTECTED / PASSWORD PROPERTY DETECTION
    Reference: EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001
    ===========================================================================
    """
    if str(prop_type or "").lower() in {"password", "secret"}:
        return True
    k = str(key or "").lower()
    return any(
        s in k
        for s in [
            "password",
            "token",
            "apikey",
            "api_key",
            "secret",
            "auth_token",
            "secret_key",
            "private_key",
            "client_secret",
        ]
    )


def _merge_customer_config_into_node(node: dict, overrides: dict, mask_sensitive: bool = False) -> dict:
    def merge_list(properties_val, overrides_dict):
        if not properties_val:
            return []
        if isinstance(properties_val, str):
            try:
                properties_val = json.loads(properties_val)
            except Exception:
                return []
        if not isinstance(properties_val, list):
            return properties_val

        # Flatten accidental nested single-item lists (e.g. [[{"key": "host"}]])
        flat_items = []
        for raw_item in properties_val:
            if isinstance(raw_item, list):
                flat_items.extend(raw_item)
            else:
                flat_items.append(raw_item)
            
        merged = []
        for item in flat_items:
            entry = item
            if isinstance(item, str):
                try:
                    entry = json.loads(item)
                except Exception:
                    continue
            if isinstance(entry, dict):
                # EPIC-NODE-PROPS-UI-001 / STORY-CHOICE-TEXTAREA-VALUES-001:
                # lift legacy comma-separated choice options into `options` before overrides
                from app.nodes.properties import normalize_choice_entry
                entry = normalize_choice_entry(dict(entry))
                key = entry.get("key")
                prop_type = entry.get("type", "")
                is_sens = _is_sensitive_property(key, prop_type)
                if key:
                    if key in overrides_dict:
                        val = overrides_dict[key]
                        if mask_sensitive and is_sens:
                            entry["default"] = "••••••••" if val else ""
                            entry["value"] = "••••••••" if val else ""
                        else:
                            entry["default"] = val
                            entry["value"] = val
                    elif mask_sensitive and is_sens:
                        if entry.get("default"):
                            entry["default"] = "••••••••"
                        if entry.get("value"):
                            entry["value"] = "••••••••"
                    
                    source_key = f"{key}_source"
                    if source_key in overrides_dict:
                        entry["source"] = overrides_dict[source_key]
                merged.append(entry)
        return merged

    node = dict(node)
    # EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001:
    # Build baseline from system_properties defaults first so user_properties inherits
    # system defaults when user_properties default/value is empty, then apply tenant overrides.
    sys_defaults = property_entries_to_dict(node.get("system_properties"))
    effective_overrides = {**sys_defaults, **(overrides or {})}
    user_props = merge_list(node.get("user_properties"), overrides or {})
    for u_entry in user_props:
        if isinstance(u_entry, dict):
            uk = u_entry.get("key")
            is_sens = _is_sensitive_property(uk, u_entry.get("type", ""))
            if uk and (u_entry.get("value") in (None, "") and u_entry.get("default") in (None, "")):
                if uk in effective_overrides and effective_overrides[uk] not in (None, ""):
                    fallback_val = effective_overrides[uk]
                    if mask_sensitive and is_sens:
                        u_entry["value"] = "••••••••"
                        u_entry["default"] = "••••••••"
                    else:
                        u_entry["value"] = fallback_val
                        u_entry["default"] = fallback_val
    system_props = merge_list(node.get("system_properties"), overrides or {})
       
    node["user_properties"] = user_props
    node["system_properties"] = system_props
    default_allow_testing = bool(sys_defaults.get("allow_node_testing", False)) if "allow_node_testing" in sys_defaults else False
    node["allow_node_testing"] = bool((overrides or {}).get("allow_node_testing", default_allow_testing))
    default_show_in_palette = bool(sys_defaults.get("show_in_palette", True)) if "show_in_palette" in sys_defaults else True
    node["show_in_palette"] = bool((overrides or {}).get("show_in_palette", default_show_in_palette))
    default_is_enabled = bool(sys_defaults.get("is_enabled", True)) if "is_enabled" in sys_defaults else True
    node["is_enabled"] = default_is_enabled
    return node


from typing import Optional


def _is_tenant_admin_user(user: User) -> bool:
    """Checks if the user is a tenant admin (role='tenant_admin' or 'admin', or has nodes:catalog:manage / nodes:catalog:clone)."""
    return (
        user.role in ("admin", "tenant_admin")
        or getattr(user, "role_type", None) in ("admin", "tenant_admin")
        or user.has_permission("nodes:catalog:manage")
        or user.has_permission("admin:nodes:manage")
    )


def _can_clone_node(user: User) -> bool:
    """Checks if the user has permission to clone a node (`system_admin`, `tenant_admin`, or `nodes:catalog:clone`)."""
    return (
        user.role in ("system_admin", "admin", "tenant_admin")
        or getattr(user, "role_type", None) in ("system_admin", "admin", "tenant_admin")
        or user.has_permission("nodes:catalog:clone")
        or user.has_permission("admin:nodes:clone")
        or user.has_permission("nodes:catalog:manage")
        or user.has_permission("admin:nodes:manage")
    )


@router.get("/customer/config")
async def get_customer_node_configs(
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all custom configurations and status of nodes for the active customer."""
    if current_user.role != "system_admin" and not _is_tenant_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    target_customer_id = customer_id
    if current_user.role != "system_admin":
        target_customer_id = current_user.customer_id
    elif current_user.role == "system_admin":
        if target_customer_id is None:
            raise HTTPException(status_code=400, detail="customer_id is required for system admin")
            
    if target_customer_id is None:
        raise HTTPException(status_code=400, detail="customer_id is required")

    stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == target_customer_id)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    
    resolved_configs = []
    for c in configs:
        # Load global node definition
        node_res = await db.execute(select(NodeDB).where(NodeDB.name == c.node_name))
        node = node_res.scalar_one_or_none()
        
        global_defaults = {}
        if node:
            global_defaults = {
                **property_entries_to_dict(node.system_properties),
                **property_entries_to_dict(node.user_properties)
            }
        
        merged_properties = {**global_defaults, **(c.properties or {})}
        resolved_configs.append({
            "node_name": c.node_name,
            "properties": merged_properties,
            "is_enabled": c.is_enabled,
            "label": c.label,
            "updated_at": c.updated_at
        })
        
    return {"configs": resolved_configs}


@router.put("/customer/config/{node_name}")
async def configure_customer_node(
    node_name: str,
    config_data: dict,
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != "system_admin" and not _is_tenant_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
        
    is_customer_config = (current_user.role != "system_admin") or (current_user.role == "system_admin" and customer_id is not None)
    base_node = None
    
    if is_customer_config:
        # update specific customer node definitions
        target_customer_id = current_user.customer_id if current_user.role != "system_admin" else customer_id
        stmt = select(CustomerNodeDB).where(
            CustomerNodeDB.customer_id == target_customer_id,
            CustomerNodeDB.node_name == node_name
        )
        result = await db.execute(stmt)
        customer_node = result.scalars().first()
        
        # Check if base node exists first
        node_exists_stmt = select(NodeDB).where(NodeDB.name == node_name)
        node_exists_res = await db.execute(node_exists_stmt)
        base_node = node_exists_res.scalars().first()
        if not base_node:
            raise HTTPException(status_code=404, detail="Node not found")
            
        if not customer_node:
            customer_node = CustomerNodeDB(
                customer_id=target_customer_id,
                node_name=node_name,
                is_enabled=True,
                properties={}
            )
            db.add(customer_node)
            
        if current_user.role != "system_admin" and not customer_node.is_enabled and config_data.get("fieldname") != "is_enabled" and "is_enabled" not in config_data:
            raise HTTPException(
                status_code=403,
                detail="This node is locked and cannot be configured because it has been disabled by the system administrator."
            )
    else:
        # system_admin configuring global node properties
        if "label" in config_data and "properties" not in config_data and "fieldname" not in config_data:
            raise HTTPException(
                status_code=400,
                detail="customer_id is required to configure customer-specific fields (label)"
            )
        stmt = select(NodeDB).where(NodeDB.name == node_name)
        result = await db.execute(stmt)
        customer_node = result.scalars().first()
        if not customer_node:
            raise HTTPException(status_code=404, detail="Node not found")
        
    # Detect selective update format
    is_selective = False
    selective_updates = {}

    if ("fieldname" in config_data or "field_name" in config_data) and "value" in config_data:
        is_selective = True
        fn = config_data.get("fieldname") or config_data.get("field_name")
        selective_updates[fn] = config_data.get("value")
    elif "updates" in config_data and isinstance(config_data["updates"], list):
        is_selective = True
        for item in config_data["updates"]:
            if isinstance(item, dict) and ("fieldname" in item or "field_name" in item) and "value" in item:
                fn = item.get("fieldname") or item.get("field_name")
                selective_updates[fn] = item.get("value")
    else:
        # Check if there are dot-notation keys (e.g. properties.api_key) in the payload
        has_dot_keys = any("." in k for k in config_data.keys())
        if has_dot_keys:
            is_selective = True
            selective_updates = config_data

    # Helper function for system_admin to update a property selectively
    def update_system_admin_property(customer_node, prop_key, val):
        sys_props = customer_node.system_properties or []
        if isinstance(sys_props, dict):
            sys_props = [{"key": k, **(v if isinstance(v, dict) else {})} for k, v in sys_props.items()]
        else:
            sys_props = [dict(item) if isinstance(item, dict) else item for item in sys_props]

        user_props = customer_node.user_properties or []
        if isinstance(user_props, dict):
            user_props = [{"key": k, **(v if isinstance(v, dict) else {})} for k, v in user_props.items()]
        else:
            user_props = [dict(item) if isinstance(item, dict) else item for item in user_props]

        is_system = prop_key.startswith("system-")
        actual_key = prop_key[7:] if is_system else prop_key

        in_sys = any(isinstance(item, dict) and item.get("key") == actual_key for item in sys_props)
        in_user = any(isinstance(item, dict) and item.get("key") == actual_key for item in user_props)

        if is_system or (in_sys and not in_user):
            found = False
            for item in sys_props:
                if isinstance(item, dict) and item.get("key") == actual_key:
                    item["default"] = val
                    item["value"] = val
                    found = True
            if not found:
                sys_props.append({"key": actual_key, "default": val, "value": val})
            customer_node.system_properties = sys_props
        else:
            found = False
            for item in user_props:
                if isinstance(item, dict) and item.get("key") == actual_key:
                    item["default"] = val
                    item["value"] = val
                    found = True
            if not found:
                user_props.append({"key": actual_key, "default": val, "value": val})
            customer_node.user_properties = user_props

    def sync_properties_selective(db_list, payload_list):
        if not isinstance(payload_list, list):
            return db_list
        if not db_list:
            db_list = []
        elif isinstance(db_list, dict):
            db_list = [{"key": k, **v} if isinstance(v, dict) else {"key": k} for k, v in db_list.items()]
        else:
            db_list = [dict(item) if isinstance(item, dict) else item for item in db_list]
        
        db_keys = {item.get("key") for item in db_list if isinstance(item, dict) and "key" in item}
        for item in payload_list:
            if not isinstance(item, dict) or "key" not in item:
                continue
            key = item["key"]
            if key in db_keys:
                for db_item in db_list:
                    if isinstance(db_item, dict) and db_item.get("key") == key:
                        db_item.update(item)
            else:
                db_list.append(item)
        return db_list

    if is_selective:
        for k, v in selective_updates.items():
            if k == "label":
                if is_customer_config:
                    customer_node.label = v
            elif k == "is_enabled":
                if is_customer_config:
                    customer_node.is_enabled = bool(v)
                elif current_user.role == "system_admin":
                    update_system_admin_property(customer_node, "system-is_enabled", bool(v))
            elif k == "allow_node_testing":
                if is_customer_config:
                    existing = dict(customer_node.properties or {})
                    existing["allow_node_testing"] = bool(v)
                    customer_node.properties = existing
                elif current_user.role == "system_admin":
                    update_system_admin_property(customer_node, "system-allow_node_testing", bool(v))
            elif k == "show_in_palette":
                if is_customer_config:
                    existing = dict(customer_node.properties or {})
                    existing["show_in_palette"] = bool(v)
                    customer_node.properties = existing
                elif current_user.role == "system_admin":
                    update_system_admin_property(customer_node, "system-show_in_palette", bool(v))
            # Disabled: NodeDB is SOT for contracts
            # elif k == "input_contract":
            #     customer_node.input_contract = v
            # elif k == "output_contract":
            #     customer_node.output_contract = v
            elif k == "user_properties" and current_user.role == "system_admin" and not is_customer_config:
                customer_node.user_properties = sync_properties_selective(customer_node.user_properties, v)
            elif k == "system_properties" and current_user.role == "system_admin" and not is_customer_config:
                customer_node.system_properties = sync_properties_selective(customer_node.system_properties, v)
            elif k == "properties":
                if is_customer_config:
                    existing = dict(customer_node.properties or {})
                    incoming = {}
                    if isinstance(v, dict):
                        incoming = v
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and "key" in item:
                                val = item.get("value") if "value" in item else item.get("default")
                                incoming[item["key"]] = val
                    
                    normalized_incoming = {}
                    for pk, pval in incoming.items():
                        norm_key = pk[7:] if pk.startswith("system-") else pk
                        normalized_incoming[norm_key] = pval
                    
                    existing.update(normalized_incoming)
                    # EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001:
                    # Allow tenant_admin to persist both system_properties and user_properties boundaries
                    customer_node.properties = dict(existing)
                elif current_user.role == "system_admin" and not is_customer_config:
                    if isinstance(v, dict):
                        for prop_key, prop_val in v.items():
                            update_system_admin_property(customer_node, prop_key, prop_val)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and "key" in item:
                                prop_key = item["key"]
                                prop_val = item.get("value") if "value" in item else item.get("default")
                                update_system_admin_property(customer_node, prop_key, prop_val)
            elif k.startswith("properties."):
                prop_key = k.split(".", 1)[1]
                if is_customer_config:
                    existing = dict(customer_node.properties or {})
                    norm_key = prop_key[7:] if prop_key.startswith("system-") else prop_key
                    existing[norm_key] = v
                    customer_node.properties = dict(existing)
                elif current_user.role == "system_admin" and not is_customer_config:
                    update_system_admin_property(customer_node, prop_key, v)
    else:
        if "properties" in config_data or "user_properties" in config_data or "system_properties" in config_data:
            properties_data = config_data.get("properties", {})
            # Standardize updates list: list of (key, value) pairs
            updates = []
            if isinstance(properties_data, dict):
                for k, val in properties_data.items():
                    pk = k[7:] if k.startswith("system-") else k
                    updates.append((pk, val))
            elif isinstance(properties_data, list):
                for item in properties_data:
                    if isinstance(item, dict) and "key" in item:
                        k = item["key"]
                        pk = k[7:] if k.startswith("system-") else k
                        val = item.get("value") if "value" in item else item.get("default")
                        updates.append((pk, val))

            # Get the set of keys that should remain
            incoming_keys = set()
            for k, _ in updates:
                actual_key = k[7:] if k.startswith("system-") else k
                incoming_keys.add(actual_key)

            if "user_properties" in config_data or "system_properties" in config_data:
                def sync_properties(db_list, payload_list):
                    if not isinstance(payload_list, list):
                        return db_list
                    if not db_list:
                        db_list = []
                    elif isinstance(db_list, dict):
                        db_list = [{"key": k, **v} if isinstance(v, dict) else {"key": k} for k, v in db_list.items()]
                    else:
                        db_list = [dict(item) if isinstance(item, dict) else item for item in db_list]
                    payload_keys = {item.get("key") for item in payload_list if isinstance(item, dict) and "key" in item}
                    # Delete properties not in payload
                    updated_list = [
                        item for item in db_list 
                        if isinstance(item, dict) and item.get("key") in payload_keys
                    ]
                    db_keys = {item.get("key") for item in updated_list if isinstance(item, dict) and "key" in item}
                    for item in payload_list:
                        if not isinstance(item, dict) or "key" not in item:
                            continue
                        key = item["key"]
                        if key in db_keys:
                            for db_item in updated_list:
                                if isinstance(db_item, dict) and db_item.get("key") == key:
                                    db_item.update(item)
                        else:
                            updated_list.append(item)
                    return updated_list

                target_node_for_props = customer_node if not is_customer_config else base_node
                can_mutate_schema = (
                    current_user.role == "system_admin"
                    or (base_node and base_node.customer_id is not None and str(base_node.customer_id) == str(current_user.customer_id))
                )
                if target_node_for_props and can_mutate_schema:
                    existing_base_ref = property_entries_to_dict(target_node_for_props.system_properties).get("__base_node__")
                    if "user_properties" in config_data:
                        target_node_for_props.user_properties = sync_properties(target_node_for_props.user_properties, config_data["user_properties"])
                    if "system_properties" in config_data:
                        synced_sys = sync_properties(target_node_for_props.system_properties, config_data["system_properties"])
                        if existing_base_ref and not any(isinstance(p, dict) and p.get("key") == "__base_node__" for p in synced_sys):
                            synced_sys.append({
                                "key": "__base_node__",
                                "type": "string",
                                "label": "Base Node",
                                "value": existing_base_ref,
                                "default": existing_base_ref,
                                "description": "Underlying executable node class reference",
                            })
                        target_node_for_props.system_properties = synced_sys
                # EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001:
                # Always persist tenant property values (both system_properties and user_properties)
                # into CustomerNodeDB.properties when configuring a customer node.
                if is_customer_config and updates:
                    customer_node.properties = {k: v for k, v in updates}
            elif not is_customer_config:
                    # Update NodeDB columns: system_properties and user_properties
                    sys_props = customer_node.system_properties
                    if isinstance(sys_props, dict):
                        sys_props = dict(sys_props)
                    elif isinstance(sys_props, list):
                        sys_props = [
                            dict(item) if isinstance(item, dict) else item 
                            for item in sys_props
                        ]
                    else:
                        sys_props = {}
                    
                    user_props = customer_node.user_properties
                    if isinstance(user_props, list):
                        user_props = [
                            dict(item) if isinstance(item, dict) else item 
                            for item in user_props
                        ]
                    elif isinstance(user_props, dict):
                        user_props = dict(user_props)
                    else:
                        user_props = []

                    # Delete properties that are NOT in incoming_keys
                    if isinstance(sys_props, dict):
                        sys_props = {k: v for k, v in sys_props.items() if k in incoming_keys}
                    elif isinstance(sys_props, list):
                        sys_props = [
                            item for item in sys_props
                            if not (isinstance(item, dict) and item.get("key") not in incoming_keys)
                        ]

                    if isinstance(user_props, dict):
                        user_props = {k: v for k, v in user_props.items() if k in incoming_keys}
                    elif isinstance(user_props, list):
                        user_props = [
                            item for item in user_props
                            if not (isinstance(item, dict) and item.get("key") not in incoming_keys)
                        ]

                    # Extract existing system keys to identify them even without prefix
                    if isinstance(sys_props, dict):
                        existing_sys_keys = set(sys_props.keys())
                    elif isinstance(sys_props, list):
                        existing_sys_keys = {
                            item.get("key") 
                            for item in sys_props 
                            if isinstance(item, dict) and "key" in item
                        }
                    else:
                        existing_sys_keys = set()

                    for k, v in updates:
                        is_system = k.startswith("system-") or k in existing_sys_keys
                        actual_key = k[7:] if k.startswith("system-") else k

                        if is_system:
                            if isinstance(sys_props, dict):
                                sys_props[actual_key] = v
                            elif isinstance(sys_props, list):
                                found = False
                                for item in sys_props:
                                    if isinstance(item, dict) and item.get("key") == actual_key:
                                        item["default"] = v
                                        item["value"] = v
                                        found = True
                                if not found:
                                    sys_props.append({"key": actual_key, "default": v, "value": v})
                        else:
                            if isinstance(user_props, dict):
                                user_props[actual_key] = v
                            elif isinstance(user_props, list):
                                found = False
                                for item in user_props:
                                    if isinstance(item, dict) and item.get("key") == actual_key:
                                        item["default"] = v
                                        item["value"] = v
                                        found = True
                                if not found:
                                    user_props.append({"key": actual_key, "default": v, "value": v})
                    
                    customer_node.system_properties = sys_props
                    customer_node.user_properties = user_props
            else:
                # EPIC-PROPS-CONTRACT-001 / STORY-PROPS-001:
                # Allow tenant_admin to update both system_properties and user_properties in CustomerNodeDB.properties
                customer_node.properties = {k: v for k, v in updates}

        if "is_enabled" in config_data:
            if is_customer_config:
                customer_node.is_enabled = config_data["is_enabled"]
        if "show_in_palette" in config_data:
            if is_customer_config:
                existing = dict(customer_node.properties or {})
                existing["show_in_palette"] = bool(config_data["show_in_palette"])
                customer_node.properties = existing
            elif current_user.role == "system_admin":
                update_system_admin_property(customer_node, "system-show_in_palette", bool(config_data["show_in_palette"]))
                
        if "input_contract" in config_data:
            customer_node.input_contract = config_data["input_contract"]
        if "output_contract" in config_data:
            customer_node.output_contract = config_data["output_contract"]
        if "label" in config_data:
            if is_customer_config:
                customer_node.label = config_data["label"]
        
    if is_customer_config:
        customer_node.updated_at = datetime.utcnow().isoformat()
        
    db.add(customer_node)
    await db.commit()
    await db.refresh(customer_node)
    
    if is_customer_config:
        global_defaults = {}
        if base_node:
            global_defaults = {
                **property_entries_to_dict(base_node.system_properties),
                **property_entries_to_dict(base_node.user_properties)
            }
        merged_properties = {**global_defaults, **(customer_node.properties or {})}
        return {
            "node_name": customer_node.node_name,
            "properties": merged_properties,
            "is_enabled": customer_node.is_enabled,
            "label": customer_node.label,
            "input_contract": customer_node.input_contract,
            "output_contract": customer_node.output_contract
        }
    else:
        return {
            "node_name": customer_node.name,
            "properties": {
                **property_entries_to_dict(customer_node.system_properties),
                **property_entries_to_dict(customer_node.user_properties)
            },
            "is_enabled": True,
            "input_contract": customer_node.input_contract,
            "output_contract": customer_node.output_contract
        }


# ==============================================================================
# BLOCK COMMENT: TENANT ADMIN NODE CLONING / NAMED NODE CONFIGURATIONS
# Reference: EPIC-PROPS-CONTRACT-001 / STORY-PROPS-002
# Description:
#     Allows Tenant Admins (and System Admins) to clone any registered base node
#     into a named node configuration (e.g. "MySQL - Sales DB", "MySQL - HR DB")
#     with pre-configured user_properties and locked system_properties,
#     registering it in NodeDB, CustomerNodeDB, and NodesRegistry.
# ==============================================================================
@router.post("/customer/clone")
async def clone_customer_node(
    payload: dict,
    customer_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_clone_node(current_user):
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Missing required permission 'nodes:catalog:clone' or Admin privileges to clone nodes",
        )

    base_node_name = (payload.get("base_node_name") or payload.get("base_node") or "").strip()
    raw_name = (payload.get("name") or "").strip()
    label = (payload.get("label") or raw_name).strip()
    description = payload.get("description")

    if not base_node_name or not raw_name:
        raise HTTPException(status_code=400, detail="Both 'base_node_name' and 'name' are required")

    import re
    clean_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_name).strip("_").lower()
    if not clean_slug:
        raise HTTPException(status_code=400, detail="Invalid node identifier")

    target_customer_id = (
        current_user.customer_id
        if current_user.role != "system_admin"
        else customer_id
    )

    base_res = await db.execute(select(NodeDB).where(NodeDB.name == base_node_name))
    base_node = base_res.scalars().first()
    if not base_node:
        raise HTTPException(status_code=404, detail=f"Base node '{base_node_name}' not found")

    existing_res = await db.execute(select(NodeDB).where(NodeDB.name == clean_slug))
    if existing_res.scalars().first():
        raise HTTPException(status_code=400, detail=f"Node identifier '{clean_slug}' already exists")

    import copy
    cloned_user_props = copy.deepcopy(
        payload.get("user_properties")
        if isinstance(payload.get("user_properties"), list)
        else (base_node.user_properties or [])
    )
    if isinstance(cloned_user_props, str):
        try:
            cloned_user_props = json.loads(cloned_user_props)
        except Exception:
            cloned_user_props = []

    cloned_sys_props = copy.deepcopy(
        payload.get("system_properties")
        if isinstance(payload.get("system_properties"), list)
        else (base_node.system_properties or [])
    )
    if isinstance(cloned_sys_props, str):
        try:
            cloned_sys_props = json.loads(cloned_sys_props)
        except Exception:
            cloned_sys_props = []
    if not isinstance(cloned_sys_props, list):
        cloned_sys_props = []

    # Flatten any nested single-item lists in cloned_sys_props
    flat_sys = []
    for item in cloned_sys_props:
        if isinstance(item, list):
            flat_sys.extend(item)
        else:
            flat_sys.append(item)
    cloned_sys_props = flat_sys

    # Determine root executable base node name
    base_sys_dict = property_entries_to_dict(base_node.system_properties)
    root_base_name = base_sys_dict.get("__base_node__") or base_node.name
    cloned_sys_props = [p for p in cloned_sys_props if not (isinstance(p, dict) and p.get("key") == "__base_node__")]
    cloned_sys_props.append({
        "key": "__base_node__",
        "type": "string",
        "label": "Base Node",
        "value": root_base_name,
        "default": root_base_name,
        "description": "Underlying executable node class reference",
    })

    incoming_props = payload.get("properties") or {}
    if isinstance(incoming_props, dict):
        if isinstance(cloned_user_props, list):
            for entry in cloned_user_props:
                if isinstance(entry, dict) and entry.get("key") in incoming_props:
                    val = incoming_props[entry["key"]]
                    entry["value"] = val
                    entry["default"] = val
        if isinstance(cloned_sys_props, list):
            for entry in cloned_sys_props:
                if isinstance(entry, dict) and entry.get("key") in incoming_props and entry.get("key") != "__base_node__":
                    val = incoming_props[entry["key"]]
                    entry["value"] = val
                    entry["default"] = val

    new_node_db = NodeDB(
        name=clean_slug,
        label=label,
        node_type=base_node.node_type or "NODE",
        description=description if description is not None else (base_node.description or ""),
        version=base_node.version or "1.0.0",
        category=base_node.category,
        group=base_node.group,
        icon=base_node.icon,
        color=base_node.color,
        badge=base_node.badge or "Configured",
        sub_label=root_base_name,
        user_properties=cloned_user_props,
        system_properties=cloned_sys_props,
        input_contract=copy.deepcopy(payload.get("input_contract") or base_node.input_contract or {}),
        output_contract=copy.deepcopy(payload.get("output_contract") or base_node.output_contract or {}),
        customer_id=str(target_customer_id) if target_customer_id is not None else None,
    )
    db.add(new_node_db)

    if target_customer_id is not None:
        new_cust_node = CustomerNodeDB(
            customer_id=str(target_customer_id),
            node_name=clean_slug,
            properties=dict(incoming_props) if isinstance(incoming_props, dict) else {},
            is_enabled=True,
            input_contract=new_node_db.input_contract,
            output_contract=new_node_db.output_contract,
            label=label,
        )
        db.add(new_cust_node)

    await db.commit()
    await db.refresh(new_node_db)

    from app.nodes.registry import NodesRegistry
    await NodesRegistry.register_cloned_node(
        cloned_name=clean_slug,
        base_node_name=str(root_base_name),
        label=label,
        description=new_node_db.description,
        user_properties=cloned_user_props,
        system_properties=cloned_sys_props,
        input_contract=new_node_db.input_contract,
        output_contract=new_node_db.output_contract,
        customer_id=new_node_db.customer_id,
        category=new_node_db.category,
        group=new_node_db.group,
        icon=new_node_db.icon,
        color=new_node_db.color,
        badge=new_node_db.badge,
        node_type=new_node_db.node_type,
    )

    return {
        "node": {
            "id": new_node_db.id,
            "name": new_node_db.name,
            "label": new_node_db.label,
            "node_type": new_node_db.node_type,
            "description": new_node_db.description,
            "version": new_node_db.version,
            "category": new_node_db.category,
            "group": new_node_db.group,
            "icon": new_node_db.icon,
            "color": new_node_db.color,
            "badge": new_node_db.badge,
            "sub_label": new_node_db.sub_label,
            "user_properties": new_node_db.user_properties,
            "system_properties": new_node_db.system_properties,
            "input_contract": new_node_db.input_contract,
            "output_contract": new_node_db.output_contract,
            "customer_id": new_node_db.customer_id,
            "is_enabled": True,
        }
    }


# BLOCK COMMENT: Non-breaking allowed nodes governance for standard users and tenant admins
@router.get("")
async def list_nodes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches registered nodes, filtered and merged by customer admin settings."""
    stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == current_user.customer_id)
    result = await db.execute(stmt)
    cust_nodes = {cn.node_name: cn for cn in result.scalars().all()}
    
    nodes = await _fetch_nodes(db, _nodes_with_categories_query())
    
    filtered_nodes = []
    for node in nodes:
        node_name = node.get("name")
        node_cust_id = node.get("customer_id")
        if current_user.role != "system_admin" and node_cust_id is not None:
            if str(node_cust_id) != str(current_user.customer_id):
                continue
        cust_node = cust_nodes.get(node_name)
        
        if current_user.role == "system_admin" or _is_tenant_admin_user(current_user):
            overrides = cust_node.properties if cust_node and cust_node.properties else {}
            merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=False)
            if cust_node is not None:
                merged["is_enabled"] = cust_node.is_enabled
            if current_user.role != "system_admin" and merged.get("is_enabled") is False:
                continue
            if "allow_node_testing" in overrides:
                merged["allow_node_testing"] = bool(overrides.get("allow_node_testing", False))
            if cust_node:
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
                if getattr(cust_node, "label", None) is not None:
                    merged["label"] = cust_node.label
            filtered_nodes.append(merged)
        else:
            # Standard users (Workflow Designers):
            # Both is_enabled (Visible to Tenant Admin) and show_in_palette (Visible to Users) default to True
            overrides = cust_node.properties if cust_node and cust_node.properties else {}
            merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=True)
            is_allowed = cust_node.is_enabled if cust_node is not None else merged.get("is_enabled", True)
            if is_allowed and merged.get("show_in_palette", True):
                merged["is_enabled"] = True
                if cust_node:
                    if cust_node.input_contract is not None:
                        merged["input_contract"] = cust_node.input_contract
                    if cust_node.output_contract is not None:
                        merged["output_contract"] = cust_node.output_contract
                    if getattr(cust_node, "label", None) is not None:
                        merged["label"] = cust_node.label
                filtered_nodes.append(merged)
                
    return {"nodes": filtered_nodes}


@router.get("/{node_name}")
async def get_node(
    node_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches a specific node definition by name, merged with customer overrides."""
    node = await _fetch_node(
        db,
        _nodes_with_categories_query().where(
            or_(NodeDB.name == node_name, cast(NodeDB.id, String) == node_name)
        ),
    )
    if not node:
        return {"error": "Node not found"}
        
    stmt = select(CustomerNodeDB).where(
        CustomerNodeDB.customer_id == current_user.customer_id,
        CustomerNodeDB.node_name == node["name"]
    )
    result = await db.execute(stmt)
    cust_node = result.scalar_one_or_none()
    
    if current_user.role != "system_admin":
        if not cust_node or not cust_node.is_enabled:
            return {"error": "Node not found or not enabled by admin"}
            
    overrides = cust_node.properties if cust_node and cust_node.properties else {}
    mask_sensitive = not (current_user.role == "system_admin" or _is_tenant_admin_user(current_user))
    merged_node = _merge_customer_config_into_node(node, overrides, mask_sensitive=mask_sensitive)
    merged_node["is_enabled"] = cust_node.is_enabled if cust_node else True
    if cust_node:
        if cust_node.input_contract is not None:
            merged_node["input_contract"] = cust_node.input_contract
        if cust_node.output_contract is not None:
            merged_node["output_contract"] = cust_node.output_contract
        if getattr(cust_node, "label", None) is not None:
            merged_node["label"] = cust_node.label
    return {"node": merged_node}


@router.get("/id/{id}")
async def get_node_by_id(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches a specific node definition by ID, merged with customer overrides."""
    node = await _fetch_node(
        db,
        _nodes_with_categories_query().where(cast(NodeDB.id, String) == id),
    )
    if not node:
        return {"error": "Node not found"}
        
    stmt = select(CustomerNodeDB).where(
        CustomerNodeDB.customer_id == current_user.customer_id,
        CustomerNodeDB.node_name == node["name"]
    )
    result = await db.execute(stmt)
    cust_node = result.scalar_one_or_none()
    
    if current_user.role != "system_admin":
        if not cust_node or not cust_node.is_enabled:
            return {"error": "Node not found or not enabled by admin"}
            
    overrides = cust_node.properties if cust_node and cust_node.properties else {}
    mask_sensitive = not (current_user.role == "system_admin" or _is_tenant_admin_user(current_user))
    merged_node = _merge_customer_config_into_node(node, overrides, mask_sensitive=mask_sensitive)
    merged_node["is_enabled"] = cust_node.is_enabled if cust_node else True
    if cust_node:
        # Disabled: NodeDB is SOT for contracts
        # if cust_node.input_contract is not None:
        #     merged_node["input_contract"] = cust_node.input_contract
        # if cust_node.output_contract is not None:
        #     merged_node["output_contract"] = cust_node.output_contract
        if getattr(cust_node, "label", None) is not None:
            merged_node["label"] = cust_node.label
    return {"node": merged_node}


async def _resolve_category_id(category_val: str, db: AsyncSession) -> str:
    if not category_val:
        return category_val
    try:
        stmt = select(CategoryDB).where(
            or_(
                cast(CategoryDB.id, String) == category_val,
                CategoryDB.group == category_val,
                CategoryDB.label == category_val
            )
        )
        result = await db.execute(stmt)
        category_obj = result.scalar_one_or_none()
        if category_obj:
            return str(category_obj.id)
    except Exception as e:
        logger.error("error_resolving_category_id", error=str(e))
    return category_val


@router.put("/{node_name}")
async def update_node(
    node_name: str,
    node_data: dict,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Updates a global node definition in the registry catalog (Super-Admin only)."""
    result = await db.execute(select(NodeDB).where(NodeDB.name == node_name))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}

    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)
    if "node_type" in node_data:
        raw_nt = str(node_data.get("node_type") or "NODE").strip().upper()
        node_data["node_type"] = "NODE" if raw_nt == "DEFAULT" or not raw_nt else raw_nt

    defaults = _defaults_from_payload(node_data)

    for key, value in node_data.items():
        if key in ["id", "name"]:
            continue
        if hasattr(node, key):
            setattr(node, key, value)

    db.add(node)
    await db.commit()
    await db.refresh(node)
    await propagate_node_defaults_to_workflows(node.name, defaults)
    logger.info("node_updated", node_name=node_name)
    return {"node": node}


@router.post("")
async def create_node(
    node_data: dict,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Creates a new global node definition in the registry catalog (Super-Admin only)."""
    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)
    raw_nt = str(node_data.get("node_type") or "NODE").strip().upper()
    node_data["node_type"] = "NODE" if raw_nt == "DEFAULT" or not raw_nt else raw_nt

    new_node = NodeDB(**{key: value for key, value in node_data.items() if key != "id" and hasattr(NodeDB, key)})
    db.add(new_node)
    await db.commit()
    await db.refresh(new_node)
    logger.info("node_created", node_name=new_node.name)
    return {"node": new_node}


@router.get("/categories/{category_id}")
async def get_nodes_by_category(
    category_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches all nodes belonging to a specific category, filtered by tenant configuration."""
    stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == current_user.customer_id)
    result = await db.execute(stmt)
    cust_nodes = {cn.node_name: cn for cn in result.scalars().all()}

    nodes = await _fetch_nodes(
        db,
        _nodes_with_categories_query().where(cast(CategoryDB.id, String) == category_id),
    )

    filtered_nodes = []
    for node in nodes:
        node_name = node.get("name")
        node_cust_id = node.get("customer_id")
        if current_user.role != "system_admin" and node_cust_id is not None:
            if str(node_cust_id) != str(current_user.customer_id):
                continue
        cust_node = cust_nodes.get(node_name)

        if current_user.role == "system_admin" or _is_tenant_admin_user(current_user):
            overrides = cust_node.properties if cust_node and cust_node.properties else {}
            merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=False)
            merged["is_enabled"] = cust_node.is_enabled if cust_node else True
            if cust_node:
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
                if getattr(cust_node, "label", None) is not None:
                    merged["label"] = cust_node.label
            filtered_nodes.append(merged)
        else:
            is_allowed = cust_node.is_enabled if cust_node else True
            if is_allowed:
                overrides = (cust_node.properties or {}) if cust_node else {}
                merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=True)
                if not merged.get("show_in_palette", True):
                    continue
                merged["is_enabled"] = True
                if cust_node:
                    if cust_node.input_contract is not None:
                        merged["input_contract"] = cust_node.input_contract
                    if cust_node.output_contract is not None:
                        merged["output_contract"] = cust_node.output_contract
                    if getattr(cust_node, "label", None) is not None:
                        merged["label"] = cust_node.label
                filtered_nodes.append(merged)

    return {"nodes": filtered_nodes}


import shutil
from pathlib import Path

@router.delete("/{node_name}")
async def delete_node(
    node_name: str,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deletes a custom node.
    Only System Admins (for global/system nodes) or Tenant Admins (for their customer-scoped nodes) can delete.
    If the node is used in workflows, it flags them unless force=True is passed.
    """
    if current_user.role != "system_admin" and not _is_tenant_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin permissions required to delete nodes")

    # Fetch the node definition
    stmt = select(NodeDB).where(NodeDB.name == node_name)
    res = await db.execute(stmt)
    node = res.scalar_one_or_none()
    
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_name}' not found")

    # Check authorization:
    if current_user.role != "system_admin":
        if node.customer_id is None or str(node.customer_id) != str(current_user.customer_id):
            raise HTTPException(status_code=403, detail="You do not have permission to delete this node")

    # Scan workflows to check if node is in use
    from app.models.db_models import WorkflowDB
    import json
    
    workflow_stmt = select(WorkflowDB)
    workflow_res = await db.execute(workflow_stmt)
    workflows = workflow_res.scalars().all()
    
    used_in_workflows = []
    for workflow in workflows:
        nodes = []
        nodes_structure_str = workflow.nodes_structure
        if nodes_structure_str:
            try:
                nodes = json.loads(nodes_structure_str)
            except Exception:
                pass
        elif workflow.definition:
            definition = workflow.definition
            if isinstance(definition, str):
                try:
                    definition = json.loads(definition)
                except Exception:
                    pass
            if isinstance(definition, dict):
                nodes = definition.get("nodes") or definition.get("nodes_structure") or []
                
        for n in nodes:
            node_data = n.get("data", {})
            n_name = node_data.get("name") or n.get("name")
            if n_name == node_name:
                used_in_workflows.append({
                    "id": workflow.id,
                    "name": workflow.name
                })
                break
                
    if used_in_workflows and not force:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "NODE_IN_USE",
                "message": f"Node '{node_name}' is currently used in active workflows. Deleting it will mark these workflows as unrunnable.",
                "workflows": used_in_workflows
            }
        )

    # Delete database records from NodeDB and CustomerNodeDB
    await db.execute(delete(CustomerNodeDB).where(CustomerNodeDB.node_name == node_name))
    await db.execute(delete(NodeDB).where(NodeDB.name == node_name))
    await db.commit()

    # Evict from NodesRegistry memory map
    from app.nodes.registry import NodesRegistry
    if node_name in NodesRegistry._nodes:
        del NodesRegistry._nodes[node_name]

    # Delete files from disk if it's a plugin node
    base_plugins_path = Path("plugins/nodes")
    clean_name = node_name
    if node.customer_id is not None:
        prefix = f"customer_{node.customer_id}_"
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):]

    target_paths = [
        base_plugins_path / "system" / clean_name,
        base_plugins_path / "client" / str(node.customer_id) / clean_name if node.customer_id is not None else None,
    ]
    
    for path in target_paths:
        if path and path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
                logger.info("deleted_plugin_directory", path=str(path))
            except Exception as e:
                logger.error("failed_to_delete_plugin_directory", path=str(path), error=str(e))

    # Synchronize all workflows runnability
    from app.workflows.service import sync_workflows_runnability
    await sync_workflows_runnability(db)

    return {"message": f"Node '{node_name}' has been successfully removed."}

@router.post("/json-samples")
async def get_json_samples(
    payload:dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
   
):
    """
    Returns a sample JSON based on the schema
    """
    return generate_sample_json(payload["schema"])

# BLOCK COMMENT: Isolated node testing endpoints with tenant safety switch (allow_node_testing)
@router.post("/test-node")
@router.post("/{node_name}/test")
@router.post("/api/nodes/test-node")
@router.post("/api/nodes/{node_name}/test")
async def test_node_directly(
    payload: dict,
    node_name: Optional[str] = None,
    current_user: User = Depends(dynamic_api_guard),
    db: AsyncSession = Depends(get_db),
    http_request: Request = None,
):
    """
    Executes a specific node directly for testing/playground purposes.
    Controlled by tenant/node property `allow_node_testing`.
    Only accessible by Admin and System Admin.
    """
    import json
    import time
    from fastapi import HTTPException
    from app.core.types.common import NodeInput
    from app.nodes.registry import NodesRegistry
    
    target_node_name = node_name or payload.get("node_name")
    if not target_node_name:
        raise HTTPException(status_code=400, detail="Missing required field 'node_name'")
        
    node = NodesRegistry.get_node(target_node_name)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{target_node_name}' not found")

    from app.api.auth.dependencies import verify_node_tenant_access
    await verify_node_tenant_access(node_name=target_node_name, current_user=current_user, db=db)

    # BLOCK COMMENT: Default disabled for isolated node testing unless explicitly enabled
    if current_user.role != "system_admin" and current_user.customer_id is not None:
        allow_testing = False
        
        # 1. Check workflow node instance level if workflow_id and agent_node_id are passed
        workflow_id = payload.get("workflow_id")
        agent_node_id = payload.get("agent_node_id") or payload.get("node_id")
        if workflow_id and agent_node_id:
            from app.models.db_models import WorkflowNodePropertyDB
            wf_prop_res = await db.execute(
                select(WorkflowNodePropertyDB).where(
                    WorkflowNodePropertyDB.workflow_id == str(workflow_id),
                    WorkflowNodePropertyDB.agent_node_id == str(agent_node_id)
                )
            )
            wf_prop_row = wf_prop_res.scalars().first()
            if wf_prop_row:
                if wf_prop_row.allow_node_testing is not None:
                    allow_testing = bool(wf_prop_row.allow_node_testing)
                elif wf_prop_row.properties and isinstance(wf_prop_row.properties, dict) and "allow_node_testing" in wf_prop_row.properties:
                    allow_testing = bool(wf_prop_row.properties["allow_node_testing"])

        # 2. Check tenant CustomerNodeDB if not determined at workflow level
        if not allow_testing:
            stmt = select(CustomerNodeDB).where(
                CustomerNodeDB.customer_id == current_user.customer_id,
                CustomerNodeDB.node_name == target_node_name
            )
            res = await db.execute(stmt)
            cust_node_row = res.scalars().first()
            if cust_node_row and cust_node_row.properties and isinstance(cust_node_row.properties, dict):
                if "allow_node_testing" in cust_node_row.properties:
                    allow_testing = bool(cust_node_row.properties.get("allow_node_testing", False))

        if not allow_testing:
            raise HTTPException(
                status_code=403,
                detail=f"Isolated node testing is disabled for node '{target_node_name}'. An administrator must enable testing for this node."
            )

    config_override = payload.get("config") or payload.get("properties") or {}
    data_val = payload #.get("data") or payload.get("input") or payload.get("input_payload")
    context = payload.get("context") or {}
    
    # Secure customer isolation: override or inject user's customer_id
    user_data = {
        "user_id": current_user.id,
        "customer_id": current_user.customer_id,
        "role": current_user.role
    }
    context["user_data"] = user_data
    context["customer_id"] = current_user.customer_id
    context["tenant_id"] = current_user.customer_id

    # DESIGN CHANGE (inbound request capture, all endpoints): server-side request
    # snapshot overrides any client-supplied context["request"] (anti-spoofing).
    trace_id = str(uuid.uuid4())
    if http_request is not None:
        context["request"] = extract_request_info(
            http_request,
            body=await http_request.body(),
            source="node_test",
            trace_id=trace_id,
            extra={
                "node_name": target_node_name,
                "user_id": current_user.id,
                "tenant_id": current_user.customer_id,
                "role": current_user.role,
            },
        )

    # If node has test method on BaseNode, run isolated test
    if hasattr(node, "test") and callable(node.test) and isinstance(data_val, dict):
        try:
            test_result = await node.test(
                test_input=data_val,
                override_properties=config_override,
                context=context,
                trace_id=trace_id,
            )
            return test_result
        except Exception as e:
            logger.exception("isolated_node_test_method_failed", node_name=target_node_name)

    # Fallback to standard node.run / node.execute
    if isinstance(data_val, (dict, list)):
        data_str = json.dumps(data_val)
    elif data_val is not None:
        data_str = str(data_val)
    else:
        data_str = ""
        
    resolved_config = node.get_resolved_properties(instance_overrides=config_override) if hasattr(node, "get_resolved_properties") else config_override

    node_input = NodeInput(
        trace_id=trace_id,
        data=data_str,
        config=resolved_config,
        context=context
    )
    
    try:
        node_output = await node.run(node_input)
        
        output_data = node_output.data
        try:
            output_data = json.loads(node_output.data)
        except Exception:
            pass
            
        return {
            "status": node_output.status,
            "data": output_data,
            "error_message": node_output.error_message,
            "error_code": node_output.error_code,
            "violations": node_output.violations,
            "metadata": node_output.metadata,
            # DESIGN CHANGE (node timing -> metadata): latency read from node metadata
            "latency_ms": (node_output.metadata or {}).get("latency_ms", 0.0)
        }
    except Exception as e:
        logger.exception("direct_node_execution_failed", node_name=target_node_name)
        raise HTTPException(status_code=500, detail=f"Direct node execution failed: {str(e)}")



