import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.db_models import NodeDB, WorkflowDB, CustomerNodeDB
from app.core.database import AsyncSessionLocal
from app.nodes.registry import NodesRegistry
from app.nodes.base import BaseNode
from app.workflows.executor import WorkflowExecutor
from app.core.cache import trace_store
from app.core.types.common import NodeInput, NodeOutput

class CustomTestNode(BaseNode):
    name: str = "customer_1_test_node"
    label: str = "Custom Test Node"
    description: str = "A mock custom node for testing"
    category: str = "Custom"
    version: str = "1.0.0"

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="success")
        
    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="success")

@pytest.mark.asyncio
async def test_custom_node_deletion_runnability_lifecycle(client: AsyncClient, system_admin_headers: dict):
    # 1. Setup mock custom node in registry and DB
    custom_node_name = "customer_1_test_node"
    
    node_instance = CustomTestNode()
    await NodesRegistry.register(node_instance)
    assert custom_node_name in NodesRegistry._nodes
    
    async with AsyncSessionLocal() as session:
        # Check if node exists in DB, insert if not
        stmt = select(NodeDB).where(NodeDB.name == custom_node_name)
        result = await session.execute(stmt)
        db_node = result.scalar_one_or_none()
        if not db_node:
            db_node = NodeDB(
                name=custom_node_name,
                label="Custom Test Node",
                node_type="NODE",
                description="Mock Node",
                version="1.0.0",
                category="1",
                customer_id=1
            )
            session.add(db_node)
            await session.commit()
            
    # 2. Setup workflow that references this custom node
    workflow_id = "test-custom-node-workflow"
    workflow_payload = {
        "id": workflow_id,
        "name": "Test Custom Node Runnability",
        "user_id": "test-user",
        "nodes": [
            {
                "id": "node-1",
                "type": "custom",
                "data": {
                    "name": custom_node_name,
                    "label": "Custom Test Node"
                }
            }
        ],
        "edges": [],
        "category": "testing"
    }
    
    # Create workflow
    create_res = await client.post("/workflows", json=workflow_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    
    # Verify workflow is runnable initially
    async with AsyncSessionLocal() as session:
        wf_res = await session.execute(select(WorkflowDB).where(WorkflowDB.id == workflow_id))
        db_wf = wf_res.scalar_one()
        assert db_wf.is_runnable is True
        
    # 3. Call DELETE /nodes/{node_name} to delete the custom node (should fail with 400 because it's in use)
    delete_res = await client.delete(f"/nodes/{custom_node_name}", headers=system_admin_headers)
    assert delete_res.status_code == 400
    assert delete_res.json()["detail"]["error_code"] == "NODE_IN_USE"
    
    # 3b. Call DELETE /nodes/{node_name}?force=true to delete it successfully
    delete_res = await client.delete(f"/nodes/{custom_node_name}?force=true", headers=system_admin_headers)
    assert delete_res.status_code == 200
    
    # 4. Verify node is removed from registry and DB
    assert custom_node_name not in NodesRegistry._nodes
    async with AsyncSessionLocal() as session:
        node_res = await session.execute(select(NodeDB).where(NodeDB.name == custom_node_name))
        assert node_res.scalar_one_or_none() is None
        
        # Verify workflow's is_runnable is marked False
        wf_res = await session.execute(select(WorkflowDB).where(WorkflowDB.id == workflow_id))
        db_wf = wf_res.scalar_one()
        assert db_wf.is_runnable is False
        
    # 5. Verify executor aborts execution cleanly
    # Load workflow config dict
    async with AsyncSessionLocal() as session:
        wf_res = await session.execute(select(WorkflowDB).where(WorkflowDB.id == workflow_id))
        db_wf = wf_res.scalar_one()
        workflow_config = {
            "id": db_wf.id,
            "name": db_wf.name,
            "is_runnable": db_wf.is_runnable,
            "customer_id": db_wf.customer_id,
            "user_id": db_wf.user_id,
            "version": str(db_wf.version),
            "nodes_structure": []
        }
        
    executor = WorkflowExecutor(workflow_config)
    with pytest.raises(ValueError) as excinfo:
        await executor.execute_async(input_content="test", trace_id="test-trace-runnability")
    assert "Workflow execution halted: Workflow is marked as not runnable due to node loading errors." in str(excinfo.value)
    
    # Verify trace is saved with failure status
    trace_raw = await trace_store.client.get("trace:test-trace-runnability")
    assert trace_raw is not None
    import json
    trace = json.loads(trace_raw)
    assert trace["status"] == "failure"
    assert "not runnable" in trace["error_message"]

    # 6. Cleanup workflow
    delete_wf_res = await client.request(
        "DELETE",
        f"/workflows/{workflow_id}",
        json={"id": "test-user", "role": "admin", "email": "test-user@example.com"},
        headers=system_admin_headers
    )
    assert delete_wf_res.status_code == 204


@pytest.mark.asyncio
async def test_customer_detail_fields_management(client: AsyncClient, system_admin_headers: dict):
    # 1. Create a customer with details
    customer_payload = {
        "name": "Acme Detail Corp",
        "domain": "acmedetail.com",
        "email": "contact@acmedetail.com",
        "address": "123 Business Rd, Suite 100",
        "contact_person": "Jane Doe",
        "color_schema": "#ff0000"
    }
    
    create_res = await client.post("/admin/customers", json=customer_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    created_cust = create_res.json()
    assert created_cust["email"] == "contact@acmedetail.com"
    assert created_cust["address"] == "123 Business Rd, Suite 100"
    assert created_cust["contact_person"] == "Jane Doe"
    cust_id = created_cust["id"]
    
    # 2. Get customers list and check fields
    list_res = await client.get("/admin/customers", headers=system_admin_headers)
    assert list_res.status_code == 200
    customers = list_res.json()
    cust_in_list = next(c for c in customers if c["id"] == cust_id)
    assert cust_in_list["email"] == "contact@acmedetail.com"
    assert cust_in_list["address"] == "123 Business Rd, Suite 100"
    assert cust_in_list["contact_person"] == "Jane Doe"
    
    # 3. Update customer details
    update_payload = {
        "email": "updated@acmedetail.com",
        "address": "456 Corporate Blvd",
        "contact_person": "Robert Smith"
    }
    update_res = await client.put(f"/admin/customers/{cust_id}", json=update_payload, headers=system_admin_headers)
    assert update_res.status_code == 200
    updated_cust = update_res.json()
    assert updated_cust["email"] == "updated@acmedetail.com"
    assert updated_cust["address"] == "456 Corporate Blvd"
    assert updated_cust["contact_person"] == "Robert Smith"
    
    # 4. Clean up customer
    delete_res = await client.delete(f"/admin/customers/{cust_id}", headers=system_admin_headers)
    assert delete_res.status_code == 204


@pytest.mark.asyncio
async def test_dynamic_customer_plugin_startup_load(client: AsyncClient, system_admin_headers: dict):
    import shutil
    import tempfile
    import os
    
    # 1. Create a customer with custom plugins enabled
    customer_payload = {
        "name": "Dynamic Plugin Tenant",
        "domain": "plugin-tenant.com",
        "custom_plugins_enabled": True,
        # Create a temp dir inside workspace to satisfy workspace constraints
        "plugin_storage_path": "./temp_customer_plugins"
    }
    
    # Ensure local directory is clean
    temp_dir_path = os.path.abspath("./temp_customer_plugins")
    if os.path.exists(temp_dir_path):
        shutil.rmtree(temp_dir_path)
    os.makedirs(temp_dir_path, exist_ok=True)

    create_res = await client.post("/admin/customers", json=customer_payload, headers=system_admin_headers)
    assert create_res.status_code == 201
    customer_id = create_res.json()["id"]

    try:
        # 2. Write a mock plugin subdirectory, manifest, and script
        plugin_name = "test_custom_startup_node"
        plugin_dir = os.path.join(temp_dir_path, plugin_name)
        os.makedirs(plugin_dir, exist_ok=True)
        
        manifest = {
            "name": plugin_name,
            "label": "Test Startup Node",
            "description": "Mock node for testing startup loading",
            "file_name": "test_node.py",
            "class_name": "TestStartupNode",
            "category": "Custom"
        }
        
        with open(os.path.join(plugin_dir, "manifest.json"), "w") as f:
            import json
            json.dump(manifest, f)
            
        code = """
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput

class TestStartupNode(BaseNode):
    name: str = "test_custom_startup_node"
    label: str = "Test Startup Node"
    description: str = "Mock node"
    category: str = "Custom"
    version: str = "1.0.0"

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="success")
        
    async def init(self) -> None:
        await super().init()
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        return NodeOutput(trace_id=inp.trace_id, data=inp.data, status="success")
"""
        with open(os.path.join(plugin_dir, "test_node.py"), "w") as f:
            f.write(code)

        # 3. Trigger registry auto discover
        await NodesRegistry.node_auto_discover()
        
        # 4. Verify in-memory registration
        registry_name = f"client_{customer_id}_{plugin_name}"
        loaded_node = NodesRegistry.get_node(registry_name)
        assert loaded_node is not None
        assert loaded_node.customer_id == customer_id
        
        # 5. Verify database registration
        async with AsyncSessionLocal() as session:
            node_res = await session.execute(select(NodeDB).where(NodeDB.name == registry_name))
            db_nodes = node_res.scalars().all()
            assert len(db_nodes) >= 1
            db_node = db_nodes[0]
            assert db_node.customer_id == customer_id
            
            # Verify join table CustomerNodeDB auto-assignment and enablement
            stmt_cn = select(CustomerNodeDB).where(
                CustomerNodeDB.customer_id == customer_id,
                CustomerNodeDB.node_name == registry_name
            )
            res_cn = await session.execute(stmt_cn)
            db_cns = res_cn.scalars().all()
            assert len(db_cns) >= 1
            db_cn = db_cns[0]
            assert db_cn.is_enabled is True

    finally:
        # Clean up database records
        async with AsyncSessionLocal() as session:
            # Delete NodeDB, CustomerNodeDB, and Customer
            registry_name = f"client_{customer_id}_{plugin_name}"
            await session.execute(
                select(NodeDB).where(NodeDB.name == registry_name)
            )
            # Remove from memory registry
            if registry_name in NodesRegistry._nodes:
                del NodesRegistry._nodes[registry_name]
                
        # Clean up temp folder
        if os.path.exists(temp_dir_path):
            shutil.rmtree(temp_dir_path)
            
        await client.delete(f"/admin/customers/{customer_id}", headers=system_admin_headers)


@pytest.mark.asyncio
async def test_custom_node_db_version_check():
    # Define a temporary mock node
    class MockVersionNode(BaseNode):
        name: str = "mock_version_node"
        label: str = "Initial Label"
        description: str = "Initial description"
        version: str = "1.0.0"
        
        async def execute(self, inp):
            pass

        async def validate_input(self, inp):
            pass

        async def init(self):
            await super().init()

    node = MockVersionNode()

    # Ensure it's clean in the DB first
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        await session.execute(delete(NodeDB).where(NodeDB.name == node.name))
        await session.commit()

    try:
        # 1. Add node first time (not present in DB)
        await NodesRegistry.add_node_to_db(node)

        # Verify added to DB
        async with AsyncSessionLocal() as session:
            stmt = select(NodeDB).where(NodeDB.name == node.name)
            res = await session.execute(stmt)
            db_node = res.scalar_one_or_none()
            assert db_node is not None
            assert db_node.label == "Initial Label"
            assert db_node.description == "Initial description"
            assert db_node.version == "1.0.0"

        # 2. Overwrite with SAME version, different fields
        node.label = "Updated Label"
        node.description = "Updated description"
        await NodesRegistry.add_node_to_db(node)

        # Verify overwritten in DB
        async with AsyncSessionLocal() as session:
            stmt = select(NodeDB).where(NodeDB.name == node.name)
            res = await session.execute(stmt)
            db_node = res.scalar_one_or_none()
            assert db_node is not None
            assert db_node.label == "Updated Label"
            assert db_node.description == "Updated description"

        # 3. Try to overwrite with DIFFERENT version
        node.label = "Should Not Be Applied"
        node.version = "1.1.0"
        await NodesRegistry.add_node_to_db(node)

        # Verify NOT overwritten in DB (still has "Updated Label" and version "1.0.0")
        async with AsyncSessionLocal() as session:
            stmt = select(NodeDB).where(NodeDB.name == node.name)
            res = await session.execute(stmt)
            db_node = res.scalar_one_or_none()
            assert db_node is not None
            assert db_node.label == "Updated Label"
            assert db_node.version == "1.0.0"

    finally:
        # Clean up
        async with AsyncSessionLocal() as session:
            from sqlalchemy import delete
            await session.execute(delete(NodeDB).where(NodeDB.name == "mock_version_node"))
            await session.commit()



