from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, or_, select
import structlog
import json
from datetime import datetime

from app.core.database import get_db
from app.models.db_models import CategoryDB, NodeDB, CustomerNodeDB
from app.nodes.properties import property_entries_to_dict
from app.workflows.store import propagate_node_defaults_to_workflows
from app.api.auth.dependencies import get_current_user, get_current_admin, get_current_system_admin
from app.core.types.users import User

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
    return [dict(row) for row in result.mappings().all()]


async def _fetch_node(db: AsyncSession, statement):
    result = await db.execute(statement)
    row = result.mappings().one_or_none()
    return dict(row) if row else None


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
            
        merged = []
        for item in properties_val:
            entry = item
            if isinstance(item, str):
                try:
                    entry = json.loads(item)
                except Exception:
                    continue
            if isinstance(entry, dict):
                key = entry.get("key")
                if key and key in overrides_dict:
                    val = overrides_dict[key]
                    if mask_sensitive and any(s in key.lower() for s in ["password", "token", "apikey", "secret", "key", "auth_token", "secret_key"]):
                        entry["default"] = "••••••••" if val else ""
                        entry["value"] = "••••••••" if val else ""
                    else:
                        entry["default"] = val
                        entry["value"] = val
                elif mask_sensitive and key:
                    if any(s in key.lower() for s in ["password", "token", "apikey", "secret", "key", "auth_token", "secret_key"]):
                        if entry.get("default"):
                            entry["default"] = "••••••••"
                        if entry.get("value"):
                            entry["value"] = "••••••••"
                merged.append(entry)
        return merged

    node = dict(node)
    user_props = merge_list(node.get("user_properties"), overrides)
    system_props = merge_list(node.get("system_properties"), overrides)
    node["user_properties"] = user_props
    node["system_properties"] = system_props
    return node


from typing import Optional

@router.get("/customer/config")
async def get_customer_node_configs(
    customer_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all custom configurations and status of nodes for the active customer."""
    if current_user.role not in ["admin", "system_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    target_customer_id = customer_id
    if current_user.role == "admin":
        target_customer_id = current_user.customer_id
    elif current_user.role == "system_admin":
        if target_customer_id is None:
            raise HTTPException(status_code=400, detail="customer_id is required for system admin")
            
    if target_customer_id is None:
        raise HTTPException(status_code=400, detail="customer_id is required")

    stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == target_customer_id)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    return {"configs": [
        {
            "node_name": c.node_name,
            "properties": c.properties,
            "is_enabled": c.is_enabled,
            "updated_at": c.updated_at
        } for c in configs
    ]}


@router.put("/customer/config/{node_name}")
async def configure_customer_node(
    node_name: str,
    config_data: dict,
    customer_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Saves node properties override and enabled status for the customer tenant."""
    if current_user.role not in ["admin", "system_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
        
    target_customer_id = customer_id or config_data.get("customer_id") or config_data.get("customerId")
    if current_user.role == "system_admin" and target_customer_id is None:
        raise HTTPException(status_code=400, detail="customer_id is required")

    if current_user.role == "admin":
        # update specific customer node definitions
        target_customer_id = current_user.customer_id
        stmt = select(CustomerNodeDB).where(
            CustomerNodeDB.customer_id == target_customer_id,
            CustomerNodeDB.node_name == node_name
        )
        result = await db.execute(stmt)
        customer_node = result.scalar_one_or_none()
        if not customer_node:
            # Check if base node exists first
            node_exists_stmt = select(NodeDB).where(NodeDB.name == node_name)
            node_exists_res = await db.execute(node_exists_stmt)
            if not node_exists_res.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Node not found")
            
            customer_node = CustomerNodeDB(
                customer_id=target_customer_id,
                node_name=node_name,
                is_enabled=True,
                properties={}
            )
            db.add(customer_node)

    elif current_user.role == "system_admin":
        # update base system property for the node in NodeDB
        stmt = select(NodeDB).where(NodeDB.name == node_name)
        result = await db.execute(stmt)
        customer_node = result.scalar_one_or_none()
        if not customer_node:
            raise HTTPException(status_code=404, detail="Node not found")
        
    if current_user.role == "admin" and not customer_node.is_enabled:
        raise HTTPException(
            status_code=403,
            detail="This node is locked and cannot be configured because it has been disabled by the system administrator."
        )
        
    if "properties" in config_data:
        properties_data = config_data["properties"]
        # Standardize updates list: list of (key, value) pairs
        updates = []
        if isinstance(properties_data, dict):
            updates = list(properties_data.items())
        elif isinstance(properties_data, list):
            for item in properties_data:
                if isinstance(item, dict) and "key" in item:
                    val = item.get("value") if "value" in item else item.get("default")
                    updates.append((item["key"], val))

        if current_user.role == "system_admin":
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
            # Update CustomerNodeDB properties column: merge the ones received
            current_properties = dict(customer_node.properties or {})
            for k, v in updates:
                current_properties[k] = v
            customer_node.properties = current_properties

    if "is_enabled" in config_data:
        if current_user.role == "admin":
            customer_node.is_enabled = config_data["is_enabled"]
            
    if "input_contract" in config_data:
        customer_node.input_contract = config_data["input_contract"]
    if "output_contract" in config_data:
        customer_node.output_contract = config_data["output_contract"]
        
    if current_user.role == "admin":
        customer_node.updated_at = datetime.utcnow().isoformat()
        
    db.add(customer_node)
    await db.commit()
    await db.refresh(customer_node)
    
    if current_user.role == "system_admin":
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
    else:
        return {
            "node_name": customer_node.node_name,
            "properties": customer_node.properties,
            "is_enabled": customer_node.is_enabled,
            "input_contract": customer_node.input_contract,
            "output_contract": customer_node.output_contract
        }


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
        cust_node = cust_nodes.get(node_name)
        
        if current_user.role in ["system_admin", "admin"]:
            overrides = cust_node.properties if cust_node and cust_node.properties else {}
            merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=False)
            merged["is_enabled"] = cust_node.is_enabled if cust_node else True
            if cust_node:
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
            filtered_nodes.append(merged)
        else:
            if cust_node and cust_node.is_enabled:
                overrides = cust_node.properties or {}
                merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=True)
                merged["is_enabled"] = True
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
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
    
    if current_user.role not in ["system_admin", "admin"]:
        if not cust_node or not cust_node.is_enabled:
            return {"error": "Node not found or not enabled by admin"}
            
    overrides = cust_node.properties if cust_node and cust_node.properties else {}
    mask_sensitive = current_user.role not in ["system_admin", "admin"]
    merged_node = _merge_customer_config_into_node(node, overrides, mask_sensitive=mask_sensitive)
    merged_node["is_enabled"] = cust_node.is_enabled if cust_node else True
    if cust_node:
        if cust_node.input_contract is not None:
            merged_node["input_contract"] = cust_node.input_contract
        if cust_node.output_contract is not None:
            merged_node["output_contract"] = cust_node.output_contract
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
    
    if current_user.role not in ["system_admin", "admin"]:
        if not cust_node or not cust_node.is_enabled:
            return {"error": "Node not found or not enabled by admin"}
            
    overrides = cust_node.properties if cust_node and cust_node.properties else {}
    mask_sensitive = current_user.role not in ["system_admin", "admin"]
    merged_node = _merge_customer_config_into_node(node, overrides, mask_sensitive=mask_sensitive)
    merged_node["is_enabled"] = cust_node.is_enabled if cust_node else True
    if cust_node:
        if cust_node.input_contract is not None:
            merged_node["input_contract"] = cust_node.input_contract
        if cust_node.output_contract is not None:
            merged_node["output_contract"] = cust_node.output_contract
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
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Updates a global node definition in the registry catalog (Super-Admin only)."""
    result = await db.execute(select(NodeDB).where(NodeDB.name == node_name))
    node = result.scalar_one_or_none()
    if not node:
        return {"error": "Node not found"}

    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)

    defaults = _defaults_from_payload(node_data)

    for key, value in node_data.items():
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
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Creates a new global node definition in the registry catalog (Super-Admin only)."""
    if "category" in node_data and node_data["category"]:
        node_data["category"] = await _resolve_category_id(str(node_data["category"]), db)

    new_node = NodeDB(**{key: value for key, value in node_data.items() if hasattr(NodeDB, key)})
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
        cust_node = cust_nodes.get(node_name)

        if current_user.role in ["system_admin", "admin"]:
            overrides = cust_node.properties if cust_node and cust_node.properties else {}
            merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=False)
            merged["is_enabled"] = cust_node.is_enabled if cust_node else True
            if cust_node:
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
            filtered_nodes.append(merged)
        else:
            if cust_node and cust_node.is_enabled:
                overrides = cust_node.properties or {}
                merged = _merge_customer_config_into_node(node, overrides, mask_sensitive=True)
                if cust_node.input_contract is not None:
                    merged["input_contract"] = cust_node.input_contract
                if cust_node.output_contract is not None:
                    merged["output_contract"] = cust_node.output_contract
                filtered_nodes.append(merged)

    return {"nodes": filtered_nodes}

