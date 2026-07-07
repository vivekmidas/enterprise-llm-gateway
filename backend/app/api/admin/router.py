# backend/app/api/admin/router.py
from fastapi import APIRouter, HTTPException, status, Depends, Response
from typing import List, Dict, Any, Optional
import structlog
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.nodes.registry import NodesRegistry
from app.nodes.base import TriggerNode
from app.nodes.built_in.webhook.base.base_webhook_agent import WebhookAgent
from app.nodes.built_in.webhook.base.scheduler_node import SchedulerAgent
from app.core.database import get_db
from app.models.db_models import CustomerDB, UserDB
from app.core.security.hash import get_password_hash
from app.api.auth.dependencies import get_current_system_admin
from app.api.admin.audit import record_audit_log
from app.core.types.users import User

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = structlog.get_logger(__name__)

@router.get("/triggers", response_model=List[Dict[str, Any]])
async def list_triggers():
    """
    Lists all registered trigger nodes and their active instances.
    """
    triggers_info = []
    for node_name, node_instance in NodesRegistry._nodes.items():
        if isinstance(node_instance, TriggerNode):
            info = {
                "name": node_instance.name,
                "description": node_instance.description,
                "version": node_instance.version,
                "category": node_instance.category,
                "node_type": node_instance.node_type,
                "properties": node_instance.properties,
                "active_instances": []
            }

            if isinstance(node_instance, WebhookAgent):
                # For WebhookAgent, list active endpoints and their server status
                for agent_node_id, server_key in node_instance._endpoint_to_server_map.items():
                    host, port = server_key
                    is_running = server_key in node_instance._server_tasks and not node_instance._server_tasks[server_key].done()
                    info["active_instances"].append({
                        "agent_node_id": agent_node_id,
                        "type": "webhook",
                        "host": host,
                        "port": port,
                        "path": f"/{node_instance.properties['path'].strip('/')}/{agent_node_id}",
                        "status": "running" if is_running else "stopped",
                        "workflow_id": node_instance._workflows.get(agent_node_id, {}).get("id")
                    })
            elif isinstance(node_instance, SchedulerAgent):
                # For SchedulerAgent, list active tasks
                for agent_node_id, task in node_instance._tasks.items():
                    is_running = not task.done()
                    info["active_instances"].append({
                        "agent_node_id": agent_node_id,
                        "type": "scheduler",
                        "status": "running" if is_running else "stopped",
                        "workflow_id": node_instance._workflows.get(agent_node_id, {}).get("id")
                    })
            
            triggers_info.append(info)
    return triggers_info

@router.post("/triggers/{node_name}/activate")
async def activate_trigger_instance(node_name: str, agent_node_id: str, workflow_config: Dict[str, Any]):
    """
    Activates a specific instance of a trigger node.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        await node_instance.activate(agent_node_id, workflow_config)
        return {"status": "success", "message": f"Trigger instance '{agent_node_id}' activated for node '{node_name}'."}
    except Exception as e:
        logger.error("failed_to_activate_trigger", node_name=node_name, agent_node_id=agent_node_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to activate trigger instance: {e}")

@router.post("/triggers/{node_name}/deactivate")
async def deactivate_trigger_instance(node_name: str, agent_node_id: str):
    """
    Deactivates a specific instance of a trigger node.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        if hasattr(node_instance, 'deactivate'):
            await node_instance.deactivate(agent_node_id)
            return {"status": "success", "message": f"Trigger instance '{agent_node_id}' deactivated for node '{node_name}'."}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Trigger node '{node_name}' does not support individual deactivation.")
    except Exception as e:
        logger.error("failed_to_deactivate_trigger", node_name=node_name, agent_node_id=agent_node_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to deactivate trigger instance: {e}")

@router.post("/triggers/{node_name}/stop_all")
async def stop_all_trigger_instances(node_name: str):
    """
    Stops all active instances for a given trigger node type.
    """
    node_instance = NodesRegistry.get_node(node_name)
    if not node_instance or not isinstance(node_instance, TriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trigger node '{node_name}' not found or is not a trigger.")
    
    try:
        if isinstance(node_instance, WebhookAgent):
            await node_instance.stop_all_servers()
        elif isinstance(node_instance, SchedulerAgent):
            for agent_node_id in list(node_instance._tasks.keys()):
                await node_instance.deactivate(agent_node_id)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Trigger node '{node_name}' does not support stopping all instances.")
        
        return {"status": "success", "message": f"All instances for trigger node '{node_name}' stopped."}
    except Exception as e:
        logger.error("failed_to_stop_all_triggers", node_name=node_name, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stop all instances for trigger node '{node_name}': {e}")


@router.get("/customers", response_model=List[Dict[str, Any]])
async def list_customers(
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Lists all customer tenants in the system (System Admin only)."""
    result = await db.execute(select(CustomerDB))
    customers = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "status": c.status,
            "icon": c.icon,
            "color_schema": c.color_schema,
            "dateadded": c.dateadded
        } for c in customers
    ]


@router.post("/customers", response_model=dict, status_code=201)
async def create_customer(
    customer_data: dict,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Creates a new customer tenant (System Admin only)."""
    name = customer_data.get("name")
    domain = customer_data.get("domain", "").strip().lower()
    
    if not name or not domain:
        raise HTTPException(status_code=400, detail="Name and domain are required")
        
    dup = await db.execute(select(CustomerDB).where(or_(CustomerDB.name == name, CustomerDB.domain == domain)))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Customer with this name or domain already exists")
        
    new_cust = CustomerDB(
        name=name,
        domain=domain,
        icon=customer_data.get("icon"),
        color_schema=customer_data.get("color_schema"),
        status="active"
    )
    db.add(new_cust)
    await db.commit()
    await db.refresh(new_cust)
    
    # Explicitly assign all existing global nodes to the new customer
    from app.models.db_models import NodeDB, CustomerNodeDB
    nodes_result = await db.execute(select(NodeDB))
    all_nodes = nodes_result.scalars().all()
    for node in all_nodes:
        cust_node = CustomerNodeDB(
            customer_id=new_cust.id,
            node_name=node.name,
            properties={},
            is_enabled=True
        )
        db.add(cust_node)
    await db.commit()

    return {
        "id": new_cust.id,
        "name": new_cust.name,
        "domain": new_cust.domain,
        "icon": new_cust.icon,
        "color_schema": new_cust.color_schema
    }



@router.put("/customers/{customer_id}", response_model=dict)
async def update_customer(
    customer_id: int,
    customer_data: dict,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Updates customer details (System Admin only)."""
    result = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    if "name" in customer_data:
        customer.name = customer_data["name"]
    if "domain" in customer_data:
        customer.domain = customer_data["domain"].strip().lower()
    if "icon" in customer_data:
        customer.icon = customer_data["icon"]
    if "color_schema" in customer_data:
        customer.color_schema = customer_data["color_schema"]
    if "status" in customer_data:
        customer.status = customer_data["status"]
        
    customer.dateupdated = datetime.utcnow().isoformat()
    await db.commit()
    await db.refresh(customer)
    
    return {
        "id": customer.id,
        "name": customer.name,
        "domain": customer.domain,
        "icon": customer.icon,
        "color_schema": customer.color_schema,
        "status": customer.status
    }


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(
    customer_id: int,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a customer tenant (System Admin only)."""
    result = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    user_count_result = await db.execute(select(UserDB.id).where(UserDB.customer_id == customer_id))
    deleted_user_ids = [row[0] for row in user_count_result.all()]
    await record_audit_log(
        db,
        current_user=current_user,
        action="customer.delete",
        resource_type="customer",
        resource_id=str(customer_id),
        customer_id=customer_id,
        details={
            "customer_name": customer.name,
            "customer_domain": customer.domain,
            "deleted_user_ids": deleted_user_ids,
        },
    )
    await db.execute(delete(UserDB).where(UserDB.customer_id == customer_id))
    await db.execute(delete(CustomerDB).where(CustomerDB.id == customer_id))
    await db.commit()
    return Response(status_code=204)


@router.post("/customers/{customer_id}/users", response_model=dict, status_code=201)
async def create_customer_user(
    customer_id: int,
    user_data: dict,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Onboards/creates a user under a customer tenant (System Admin only)."""
    email = user_data.get("email")
    password = user_data.get("password")
    name = user_data.get("name")
    role = user_data.get("role", "admin")
    
    if not email or not password or not name:
        raise HTTPException(status_code=400, detail="Email, password, and name are required")
        
    result = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")
        
    dup = await db.execute(select(UserDB).where(UserDB.email_id == email))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")
        
    hashed_password = get_password_hash(password)
    new_user = UserDB(
        username=email,
        email_id=email,
        password=hashed_password,
        name=name,
        role=role,
        customer_id=customer_id,
        status="active"
    )
    db.add(new_user)
    await db.flush()
    await record_audit_log(
        db,
        current_user=current_user,
        action="user.create",
        resource_type="user",
        resource_id=str(new_user.id),
        customer_id=customer_id,
        details={
            "email": email,
            "role": role,
            "created_under_customer_endpoint": True,
        },
    )
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "email": new_user.email_id,
        "name": new_user.name,
        "role": new_user.role,
        "customer_id": new_user.customer_id
    }


@router.get("/customers/{customer_id}/nodes", response_model=dict)
async def get_customer_nodes(
    customer_id: int,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all node configs and enablement status for a customer (System Admin only)."""
    # Verify customer exists
    cust_res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    if not cust_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.db_models import CustomerNodeDB, NodeDB
    from app.nodes.properties import property_entries_to_dict
    stmt = select(CustomerNodeDB).where(CustomerNodeDB.customer_id == customer_id)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    
    resolved_configs = []
    for c in configs:
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
            "updated_at": c.updated_at
        })
        
    return {"configs": resolved_configs}


@router.put("/customers/{customer_id}/nodes", response_model=dict)
async def configure_customer_nodes_bulk(
    customer_id: int,
    payload: dict,
    current_user: User = Depends(get_current_system_admin),
    db: AsyncSession = Depends(get_db)
):
    """Batch updates/saves node assignments for a customer (System Admin only)."""
    # Verify customer exists
    cust_res = await db.execute(select(CustomerDB).where(CustomerDB.id == customer_id))
    if not cust_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.db_models import CustomerNodeDB
    nodes_data = payload.get("nodes", [])
    
    for item in nodes_data:
        node_name = item.get("node_name")
        is_enabled = item.get("is_enabled", True)
        properties = item.get("properties", {})
        
        # Check if row exists
        stmt = select(CustomerNodeDB).where(
            CustomerNodeDB.customer_id == customer_id,
            CustomerNodeDB.node_name == node_name
        )
        res = await db.execute(stmt)
        customer_node = res.scalar_one_or_none()
        
        if not customer_node:
            customer_node = CustomerNodeDB(
                customer_id=customer_id,
                node_name=node_name
            )
            db.add(customer_node)
            
        customer_node.is_enabled = is_enabled
        if "properties" in item:
            customer_node.properties = properties
            
        customer_node.updated_at = datetime.utcnow().isoformat()
        
    await db.commit()
    return {"status": "success"}
