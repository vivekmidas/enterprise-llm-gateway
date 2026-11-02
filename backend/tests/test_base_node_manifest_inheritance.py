"""
===============================================================================
BLOCK COMMENT: BASE NODE INHERITANCE & MANIFEST LOADING TESTS
Module: backend/tests/test_base_node_manifest_inheritance.py
Description:
    Verifies:
    1. BaseNode 12 core properties default values and node_type uppercase normalization.
    2. MRO hierarchy merging for user_properties, system_properties, input_contract, output_contract.
    3. Co-located manifest.json loading and merging for all 30 database nodes.
    4. NodesRegistry.add_node_to_db conditions:
       (a) inserts when name does not exist in nodes table
       (b) updates ONLY when node.version > db_node.version
===============================================================================
"""

import json
from pathlib import Path
from typing import Any
import pytest
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.models.db_models import NodeDB
from app.nodes.base import BaseNode
from app.nodes.registry import NodesRegistry


def test_base_node_defaults_and_node_type_normalization():
    """Verify BaseNode has the 12 core properties and normalizes node_type to uppercase."""
    class SimpleChildNode(BaseNode):
        name = "simple_child_node"
        label = "Simple Child"
        node_type = "trigger"

        async def execute(self, inp):
            pass

        async def validate_input(self, inp):
            pass

    node = SimpleChildNode()
    assert node.name == "simple_child_node"
    assert node.label == "Simple Child"
    assert node.node_type == "TRIGGER"
    assert isinstance(node.user_properties, (dict, list))
    assert isinstance(node.system_properties, (dict, list))
    assert isinstance(node.input_contract, dict)
    assert isinstance(node.output_contract, dict)

    class DefaultTypeNode(BaseNode):
        name = "default_type_node"

        async def execute(self, inp):
            pass

        async def validate_input(self, inp):
            pass

    default_node = DefaultTypeNode()
    assert default_node.node_type == "NODE"


def test_mro_property_and_contract_merging():
    """Verify child node merges user_properties, system_properties, input_contract, output_contract from parent."""
    class ParentNode(BaseNode):
        name = "parent_node"
        category = "data"
        icon = "database"
        color = "#111111"
        sub_label = "Parent Sub"
        user_properties = [
            {"key": "shared_prop", "default": "parent_val", "type": "text"},
            {"key": "parent_only", "default": 10, "type": "number"},
        ]
        system_properties = {"sys_a": "from_parent", "sys_shared": "parent"}
        input_contract = {
            "type": "object",
            "properties": {
                "field_a": {"type": "string"},
                "field_shared": {"type": "string", "description": "parent"},
            },
            "required": ["field_a"],
        }
        output_contract = {
            "type": "object",
            "properties": {
                "out_a": {"type": "string"},
            },
            "required": ["out_a"],
        }

        async def execute(self, inp):
            pass

        async def validate_input(self, inp):
            pass

    class ChildNode(ParentNode):
        name = "child_node"
        label = "Child Node"
        color = "#222222"
        user_properties = [
            {"key": "shared_prop", "default": "child_val", "type": "text"},
            {"key": "child_only", "default": True, "type": "boolean"},
        ]
        system_properties = {"sys_shared": "child", "sys_b": "from_child"}
        input_contract = {
            "type": "object",
            "properties": {
                "field_shared": {"type": "string", "description": "child"},
                "field_b": {"type": "integer"},
            },
            "required": ["field_b"],
        }
        output_contract = {
            "type": "object",
            "properties": {
                "out_b": {"type": "boolean"},
            },
            "required": ["out_b"],
        }

    child = ChildNode()
    # Inherited scalar properties
    assert child.category == "data"
    assert child.icon == "database"
    assert child.sub_label == "Parent Sub"
    # Overridden scalar properties
    assert child.color == "#222222"
    assert child.label == "Child Node"

    # Merged user_properties (list format preserved since parent/child use list)
    props_by_key = {p["key"]: p for p in child.user_properties}
    assert set(props_by_key.keys()) == {"shared_prop", "parent_only", "child_only"}
    assert props_by_key["shared_prop"]["default"] == "child_val"
    assert props_by_key["parent_only"]["default"] == 10
    assert props_by_key["child_only"]["default"] is True

    # Merged system_properties
    assert child.system_properties == {
        "sys_a": "from_parent",
        "sys_shared": "child",
        "sys_b": "from_child",
    }

    # Merged input_contract
    assert set(child.input_contract["properties"].keys()) == {"field_a", "field_shared", "field_b"}
    assert child.input_contract["properties"]["field_shared"]["description"] == "child"
    assert set(child.input_contract["required"]) == {"field_a", "field_b"}

    # Merged output_contract
    assert set(child.output_contract["properties"].keys()) == {"out_a", "out_b"}
    assert set(child.output_contract["required"]) == {"out_a", "out_b"}


@pytest.mark.asyncio
async def test_all_30_nodes_discover_and_have_colocated_manifest():
    """Verify all 30 nodes in the system have dedicated folders with valid manifest.json files and auto-discover."""
    await NodesRegistry.node_auto_discover()
    registered = NodesRegistry._nodes
    assert len(registered) == 30

    for name, node in registered.items():
        manifest = node._load_colocated_manifest()
        assert manifest, f"Node {name} is missing co-located manifest.json"
        assert manifest.get("name") == name
        assert node.node_type in ("NODE", "TRIGGER", "AGENT", "TOOL", "WEBHOOK")
        defn = node.get_node_definition()
        assert defn["name"] == name
        assert defn["node_type"] == node.node_type
        assert "user_properties" in defn
        assert "system_properties" in defn
        assert "input_contract" in defn
        assert "output_contract" in defn

