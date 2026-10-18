import abc
import base64
import json
import time
from functools import cached_property
from typing import Any, Dict, List, Optional, Union, Set
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.db_models import NodeDB

try:
    from jinja2.nativetypes import NativeTemplate
except ImportError:
    # Fallback to standard Template if nativetypes is unavailable
    from jinja2 import Template as NativeTemplate
import structlog
from app.nodes.properties import property_entries_to_dict
from app.core.types.common import NodeInput,NodeOutput
from app.nodes.contracts import validate_contract
from app.utils.file_utils import load_file_bytes, extract_document_text

class JinjaFallbackDict(dict):
    def __init__(self, fallback_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback_value = fallback_value
        self._protected = {
            'range', 'dict', 'lipsum', 'cycler', 'joiner', 'namespace',
            'true', 'false', 'none', 'True', 'False', 'None',
            'context', 'metadata', 'config', 'loop', 'self'
        }

    def _should_fallback(self, key: str) -> bool:
        if key in self._protected:
            return False
        # Avoid overriding python built-ins
        import builtins
        if hasattr(builtins, key):
            return False
        return isinstance(self.fallback_value, (str, int, float))

    def __getitem__(self, key):
        if key in self:
            return super().__getitem__(key)
        if self._should_fallback(key):
            return self.fallback_value
        raise KeyError(key)

    def get(self, key, default=None):
        if key in self:
            return super().get(key)
        if self._should_fallback(key):
            return self.fallback_value
        return default

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return self._should_fallback(key)

# ==============================================================================
# BLOCK COMMENT: STANDARDIZED BASE NODE & HIERARCHICAL PROPERTY INHERITANCE
# Reference: EPIC-NODE-BASE-001 / STORY-NODE-INIT-001
# Description:
#     1. Standardizes the 12 core node properties on BaseNode:
#        (user_properties, system_properties, input_contract, output_contract,
#         name, label, node_type [default "NODE", uppercase], description,
#         category, icon, color, sub_label).
#     2. Merges user_properties, system_properties, input_contract, and
#        output_contract across the class MRO hierarchy (parent -> child) so
#        child node definitions extend base/parent definitions and override
#        matching keys.
#     3. Supports optional co-located manifest.json (<node_dir>/<node_name>/manifest.json
#        or <node_dir>/manifest.json) as part of the node definition.
#     4. Preserves unmutated schema definitions (_definition_user_properties,
#        _definition_system_properties) for NodeDB initialization & version upgrades
#        before init() flattens runtime properties into dicts.
# ==============================================================================
class _BaseNodeMeta(type(BaseModel), abc.ABCMeta):
    """
    Metaclass that allows BaseNode subclasses to override base node properties
    either with or without explicit type annotations.
    """
    def __new__(mcs, cls_name, bases, namespace, **kwargs):
        base_fields = {}
        for base in reversed(bases):
            if hasattr(base, "model_fields"):
                for fname, finfo in base.model_fields.items():
                    base_fields[fname] = finfo.annotation or Any
            for k, v in getattr(base, "__annotations__", {}).items():
                base_fields.setdefault(k, v)

        if base_fields:
            annotations = dict(namespace.get("__annotations__", {}))
            for attr_name, attr_val in list(namespace.items()):
                if (
                    attr_name in base_fields
                    and attr_name not in annotations
                    and not callable(attr_val)
                    and not isinstance(attr_val, (property, cached_property, classmethod, staticmethod))
                ):
                    annotations[attr_name] = Any
            namespace["__annotations__"] = annotations

        return super().__new__(mcs, cls_name, bases, namespace, **kwargs)


class BaseNode(BaseModel, abc.ABC, metaclass=_BaseNodeMeta):
    """
    Standardized Base Class for all Enterprise LLM Gateway nodes.

    --- DISTINCTION BETWEEN PROPERTIES AND CONTRACTS ---
    1. User Properties (properties ):
       Business logic settings configured by users in the Workflow Builder.
       Example: 'system_prompt', 'temperature', 'table_name'.

    2. System Properties (system_properties):
       Infrastructure settings configured by Admins in the Node Registry.
       Example: 'port', 'host', 'worker_count', 'timeout_ms'.

    3. Contracts (input_contract & output_contract):
       These define the DATA PAYLOAD structure (Run-time).
       Example: 'user_query', 'document_text', 'extracted_entities'.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "base_node"       # Machine identifier
    label: str = "Base Node"      # UI-facing display name (matches frontend 'label')
    description: str = "Standard node base"
    version: str = "1.0.0"
    category: str = "Custom"       # Internal functional category
    node_type: str = "NODE"        # TRIGGER, TOOL, CONNECTOR, or NODE (case-insensitive, stored uppercase)
    group: str = "Custom"          # UI grouping (matches frontend 'group')
    customer_id: Optional[Union[int, str]] = None # Scoped customer ID for custom tenant plugins

    # Contract and Envelope definitions
    input_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"user_id": {"required": True}}
    output_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"result": {"type": "string"}}

    # Visual properties for the UI (aligned with frontend BaseNodeData)
    icon: str = "bot"              # Name of the icon to be mapped in frontend
    color: str = "#5E0CEC"         # Brand color (hex code)
    badge: Optional[str] = "Node"  # Optional badge text (e.g., "Model")
    sub_label: Optional[str] = None # Optional sub-label
    user_properties: Union[List[Dict[str, Any]], Dict[str, Any]] = Field(default_factory=dict) # Default configuration values / schema
    system_properties: Union[List[Dict[str, Any]], Dict[str, Any]] = Field(default_factory=dict) # Admin-only infra settings / schema
    properties: Dict[str, Any] = Field(default_factory=dict) # Unified properties list

    _definition_user_properties: Any = PrivateAttr(default=None)
    _definition_system_properties: Any = PrivateAttr(default=None)
    _definition_input_contract: Dict[str, Any] = PrivateAttr(default_factory=dict)
    _definition_output_contract: Dict[str, Any] = PrivateAttr(default_factory=dict)

    def __init__(self, **data):
        explicit_user_props = data.get("user_properties", None)
        explicit_sys_props = data.get("system_properties", None)
        explicit_in_contract = data.get("input_contract", None)
        explicit_out_contract = data.get("output_contract", None)
        super().__init__(**data)
        self._resolve_node_definition(
            explicit_user_props=explicit_user_props,
            explicit_sys_props=explicit_sys_props,
            explicit_in_contract=explicit_in_contract,
            explicit_out_contract=explicit_out_contract,
            explicit_data=data,
        )

    @staticmethod
    def _extract_class_field_default(cls_obj: type, field_name: str) -> Any:
        """Extracts a clean copy of a field default directly defined on `cls_obj`."""
        import copy
        if field_name in cls_obj.__dict__:
            raw = cls_obj.__dict__[field_name]
            if hasattr(raw, "default") or hasattr(raw, "default_factory"):
                val = getattr(raw, "default", None)
                if val is None or "Undefined" in val.__class__.__name__:
                    factory = getattr(raw, "default_factory", None)
                    val = factory() if callable(factory) else None
                return copy.deepcopy(val)
            return copy.deepcopy(raw)

        # Fallback: check Pydantic __annotations__ / model_fields if annotated with default on this class
        if hasattr(cls_obj, "model_fields") and field_name in cls_obj.model_fields:
            # Only return if this class actually overrode the field or is BaseNode
            field_info = cls_obj.model_fields[field_name]
            parent_fields = {}
            for base in cls_obj.__bases__:
                if hasattr(base, "model_fields"):
                    parent_fields.update(base.model_fields)
            if cls_obj is BaseNode or parent_fields.get(field_name) is not field_info:
                val = getattr(field_info, "default", None)
                if val is None or "Undefined" in val.__class__.__name__:
                    factory = getattr(field_info, "default_factory", None)
                    val = factory() if callable(factory) else None
                return copy.deepcopy(val)
        return None

    @classmethod
    def merge_property_definitions(cls, parent_props: Any, child_props: Any) -> Any:
        """
        Merges parent and child property definitions (schema lists or dicts).
        Child properties override parent properties with the same 'key'; new keys are appended.
        """
        import copy
        if not parent_props and not child_props:
            return [] if isinstance(child_props, list) or isinstance(parent_props, list) else {}
        if not parent_props:
            return copy.deepcopy(child_props)
        if not child_props:
            return copy.deepcopy(parent_props)

        if isinstance(parent_props, dict) and isinstance(child_props, dict):
            return {**copy.deepcopy(parent_props), **copy.deepcopy(child_props)}

        def _to_schema_list(props: Any) -> List[Dict[str, Any]]:
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except Exception:
                    return []
            if isinstance(props, dict):
                return [{"key": k, "default": v} for k, v in props.items()]
            if isinstance(props, list):
                out = []
                for item in props:
                    if isinstance(item, str):
                        try:
                            item = json.loads(item)
                        except Exception:
                            continue
                    if isinstance(item, dict):
                        out.append(copy.deepcopy(item))
                return out
            return []

        parent_list = _to_schema_list(parent_props)
        child_list = _to_schema_list(child_props)

        merged_by_key: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        unnamed: List[Dict[str, Any]] = []

        for entry in parent_list:
            key = entry.get("key")
            if key:
                if key not in merged_by_key:
                    order.append(key)
                merged_by_key[key] = entry
            else:
                unnamed.append(entry)

        for entry in child_list:
            key = entry.get("key")
            if key:
                if key in merged_by_key:
                    merged_by_key[key] = {**merged_by_key[key], **entry}
                else:
                    order.append(key)
                    merged_by_key[key] = entry
            else:
                unnamed.append(entry)

        return [merged_by_key[k] for k in order] + unnamed

    @classmethod
    def merge_contract_definitions(cls, parent_contract: Optional[Dict[str, Any]], child_contract: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merges parent and child contract definitions across class hierarchy.
        Child rules/properties override parent rules/properties with the same field name.
        """
        import copy
        if not parent_contract and not child_contract:
            return {}
        if not parent_contract:
            return copy.deepcopy(child_contract) if isinstance(child_contract, dict) else {}
        if not child_contract:
            return copy.deepcopy(parent_contract) if isinstance(parent_contract, dict) else {}

        p = copy.deepcopy(parent_contract)
        c = copy.deepcopy(child_contract)

        # Case 1: Both use flat 'rules' list format
        if isinstance(p.get("rules"), list) and isinstance(c.get("rules"), list):
            rules_by_name: Dict[str, Dict[str, Any]] = {}
            rule_order: List[str] = []
            extra_rules: List[Dict[str, Any]] = []

            for r in p["rules"]:
                if isinstance(r, dict):
                    fname = r.get("field_name") or r.get("name")
                    if fname:
                        if fname not in rules_by_name:
                            rule_order.append(fname)
                        rules_by_name[fname] = r
                    else:
                        extra_rules.append(r)

            for r in c["rules"]:
                if isinstance(r, dict):
                    fname = r.get("field_name") or r.get("name")
                    if fname:
                        if fname in rules_by_name:
                            rules_by_name[fname] = {**rules_by_name[fname], **r}
                        else:
                            rule_order.append(fname)
                            rules_by_name[fname] = r
                    else:
                        extra_rules.append(r)

            merged = {**p, **c}
            merged["rules"] = [rules_by_name[k] for k in rule_order] + extra_rules
            return merged

        # Case 2: JSON Schema format with 'properties'
        if isinstance(p.get("properties"), dict) and isinstance(c.get("properties"), dict):
            merged = {**p, **c}
            merged["properties"] = {**p["properties"], **c["properties"]}
            if isinstance(p.get("required"), list) or isinstance(c.get("required"), list):
                req_p = p.get("required") if isinstance(p.get("required"), list) else []
                req_c = c.get("required") if isinstance(c.get("required"), list) else []
                merged["required"] = list(dict.fromkeys(req_p + req_c))
            return merged

        # Case 3: Generic dict contract merge (if same format) or child override
        if ("rules" in p) != ("rules" in c):
            return c
        return {**p, **c}

    def _load_colocated_manifest(self) -> Optional[Dict[str, Any]]:
        """
        Loads an optional manifest.json co-located with the node class definition
        (e.g. <module_dir>/<node_name>/manifest.json or <module_dir>/manifest.json).
        """
        if self.__class__.__name__ == "LazyPluginNode":
            return None
        try:
            import inspect
            from pathlib import Path
            cls_file = inspect.getfile(self.__class__)
            if not cls_file:
                return None
            module_dir = Path(cls_file).resolve().parent
            candidates = [
                module_dir / self.name / "manifest.json",
                module_dir / "manifest.json",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    with open(candidate, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    if isinstance(manifest, dict):
                        m_name = manifest.get("name")
                        m_cls = manifest.get("class_name")
                        # Match if inside <node_name>/manifest.json or if manifest targets this node/class
                        if candidate.parent.name == self.name or m_name == self.name or m_cls == self.__class__.__name__:
                            return manifest
        except Exception:
            pass
        return None

    def _resolve_node_definition(
        self,
        explicit_user_props: Any = None,
        explicit_sys_props: Any = None,
        explicit_in_contract: Any = None,
        explicit_out_contract: Any = None,
        explicit_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Resolves and merges node properties, contracts, and metadata across the
        BaseNode class hierarchy (MRO) and optional co-located manifest.json.
        """
        import copy
        mro_classes = [c for c in reversed(self.__class__.__mro__) if issubclass(c, BaseNode)]

        merged_user_props: Any = None
        merged_sys_props: Any = None
        merged_in_contract: Dict[str, Any] = {}
        merged_out_contract: Dict[str, Any] = {}

        for cls_obj in mro_classes:
            cls_user = self._extract_class_field_default(cls_obj, "user_properties")
            if cls_user:
                merged_user_props = self.merge_property_definitions(merged_user_props, cls_user)

            cls_sys = self._extract_class_field_default(cls_obj, "system_properties")
            if cls_sys:
                merged_sys_props = self.merge_property_definitions(merged_sys_props, cls_sys)

            cls_in = self._extract_class_field_default(cls_obj, "input_contract")
            if cls_in:
                merged_in_contract = self.merge_contract_definitions(merged_in_contract, cls_in)

            cls_out = self._extract_class_field_default(cls_obj, "output_contract")
            if cls_out:
                merged_out_contract = self.merge_contract_definitions(merged_out_contract, cls_out)

        # Merge explicit kwargs passed to __init__
        if explicit_user_props is not None:
            merged_user_props = self.merge_property_definitions(merged_user_props, explicit_user_props)
        if explicit_sys_props is not None:
            merged_sys_props = self.merge_property_definitions(merged_sys_props, explicit_sys_props)
        if explicit_in_contract is not None:
            merged_in_contract = self.merge_contract_definitions(merged_in_contract, explicit_in_contract)
        if explicit_out_contract is not None:
            merged_out_contract = self.merge_contract_definitions(merged_out_contract, explicit_out_contract)

        # Merge optional co-located manifest.json if present alongside node definition
        manifest = self._load_colocated_manifest()
        if manifest:
            explicit_keys = set((explicit_data or {}).keys())
            for scalar_key in ("name", "label", "description", "version", "category", "node_type", "group", "icon", "color", "badge", "sub_label"):
                if scalar_key in manifest and manifest[scalar_key] is not None and scalar_key not in explicit_keys:
                    setattr(self, scalar_key, manifest[scalar_key])
            if "user_properties" in manifest:
                merged_user_props = self.merge_property_definitions(merged_user_props, manifest["user_properties"])
            if "system_properties" in manifest:
                merged_sys_props = self.merge_property_definitions(merged_sys_props, manifest["system_properties"])
            if "input_contract" in manifest:
                merged_in_contract = self.merge_contract_definitions(merged_in_contract, manifest["input_contract"])
            if "output_contract" in manifest:
                merged_out_contract = self.merge_contract_definitions(merged_out_contract, manifest["output_contract"])

        # Normalize node_type: case-insensitive, default "NODE", always uppercase
        raw_node_type = (self.node_type or "NODE").strip()
        if raw_node_type.lower() == "default" or not raw_node_type:
            raw_node_type = "NODE"
        self.node_type = raw_node_type.upper()

        self.user_properties = merged_user_props if merged_user_props is not None else {}
        self.system_properties = merged_sys_props if merged_sys_props is not None else {}
        self.input_contract = merged_in_contract
        self.output_contract = merged_out_contract

        # Store unmutated schema definitions for DB sync
        self._definition_user_properties = copy.deepcopy(self.user_properties) if self.user_properties else []
        self._definition_system_properties = copy.deepcopy(self.system_properties) if self.system_properties else []
        self._definition_input_contract = copy.deepcopy(self.input_contract)
        self._definition_output_contract = copy.deepcopy(self.output_contract)

    def get_node_definition(self) -> Dict[str, Any]:
        """
        Returns the complete, unmutated node definition (all 12 core properties + metadata)
        used to initialize or upgrade the node in the `nodes` table.
        """
        import copy
        user_props = self._definition_user_properties
        if user_props is None:
            user_props = self.user_properties if isinstance(self.user_properties, list) else []
        sys_props = self._definition_system_properties
        if sys_props is None:
            sys_props = self.system_properties if isinstance(self.system_properties, list) else []

        norm_node_type = (self.node_type or "NODE").strip().upper()
        if norm_node_type == "DEFAULT":
            norm_node_type = "NODE"

        return {
            "name": self.name,
            "label": self.label,
            "node_type": norm_node_type,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "group": self.group,
            "icon": self.icon or "bot",
            "color": self.color or "#5E0CEC",
            "badge": self.badge,
            "sub_label": self.sub_label,
            "user_properties": copy.deepcopy(user_props),
            "system_properties": copy.deepcopy(sys_props),
            "input_contract": copy.deepcopy(self._definition_input_contract if self._definition_input_contract is not None else self.input_contract),
            "output_contract": copy.deepcopy(self._definition_output_contract if self._definition_output_contract is not None else self.output_contract),
            "customer_id": self.customer_id,
        }

    @cached_property
    def logger(self):
        """
        Returns a logger named after the node class with the node name bound to it.
        This allows all inheriting nodes to use self.logger without manual setup.
        """
        return structlog.get_logger(self.__class__.__name__).bind(node_name=self.name)

    def get_label(self) -> str:
        return self.label

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_properties(self) -> List[Dict[str, Any]]:
        """Returns the property schema definition for the UI."""
        return getattr(self, "user_properties")

    async def _get_db_node_data(self) -> Dict[str, Any]:
        """Fetches properties and metadata for this node type from the global catalog in the DB."""
        import sys
        if "pytest" in sys.modules:
            return {}
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.db_models import NodeDB
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(NodeDB).where(NodeDB.name == self.name)
                result = await session.execute(stmt)
                db_node = result.scalar_one_or_none()
                if db_node:
                    return {
                        "name": db_node.name,
                        "label": db_node.label,
                        "node_type": (db_node.node_type or "NODE").upper(),
                        "description": db_node.description,
                        "category": db_node.category,
                        "icon": db_node.icon,
                        "color": db_node.color,
                        "sub_label": db_node.sub_label,
                        "user_properties": db_node.user_properties or {},
                        "system_properties": db_node.system_properties or {},
                        "input_contract": db_node.input_contract or {},
                        "output_contract": db_node.output_contract or {},
                    }
        except Exception as e:
            self.logger.warning("db_properties_fetch_failed", error=str(e))
        return {}

    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties and contracts from DB.
        Should be called during registration/discovery after DB synchronization.
        """
        self.logger.info(f"Initiating node start {self.name}")

        self.node_type = (self.node_type or "NODE").strip().upper()
        if self.node_type == "DEFAULT":
            self.node_type = "NODE"

        user_props_dict = property_entries_to_dict(self.user_properties)
        system_props_dict = property_entries_to_dict(self.system_properties)

        db_data = await self._get_db_node_data()
        if db_data:
            if db_data.get("label"):
                self.label = db_data["label"]
            if db_data.get("node_type"):
                self.node_type = str(db_data["node_type"]).strip().upper()
            if db_data.get("description") is not None:
                self.description = db_data["description"]
            if db_data.get("icon"):
                self.icon = db_data["icon"]
            if db_data.get("color"):
                self.color = db_data["color"]
            if db_data.get("sub_label") is not None:
                self.sub_label = db_data["sub_label"]
            if db_data.get("user_properties"):
                user_props_dict.update(property_entries_to_dict(db_data.get("user_properties")))
            if db_data.get("system_properties"):
                system_props_dict.update(property_entries_to_dict(db_data.get("system_properties")))
            if db_data.get("input_contract"):
                self.input_contract = db_data.get("input_contract")
            if db_data.get("output_contract"):
                self.output_contract = db_data.get("output_contract")

        self.user_properties = user_props_dict
        self.system_properties = system_props_dict

        # Unified merge: User properties override System properties
        self.properties = {**self.system_properties, **self.user_properties}
        self.logger.info(f"Initiating node ended {self.name}")

    # BLOCK COMMENT: BaseNode property precedence resolution & isolated test method
    def get_resolved_properties(
        self,
        instance_overrides: Optional[Dict[str, Any]] = None,
        tenant_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Native property resolution inherited by all node subclasses.
        Precedence: Instance Overrides > Tenant Overrides > Global Code/DB Defaults.
        System properties remain protected.
        """
        global_user = property_entries_to_dict(getattr(self, "user_properties", {}))
        global_system = property_entries_to_dict(getattr(self, "system_properties", {}))
        tenant_user = tenant_overrides or {}
        instance_user = instance_overrides or {}

        resolved_user = {**global_user, **tenant_user, **instance_user}
        return {**global_system, **resolved_user}

    async def test(
        self,
        test_input: Any,
        override_properties: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes single node in isolation with transient properties without graph state.
        """
        resolved_props = self.get_resolved_properties(instance_overrides=override_properties)

        if isinstance(test_input, (dict, list)):
            data_str = json.dumps(test_input)
        elif isinstance(test_input, str):
            data_str = test_input
        elif test_input is not None:
            data_str = str(test_input)
        else:
            data_str = ""

        trace_id = f"test-{self.name}-{int(time.time())}"
        node_input = NodeInput(
            trace_id=trace_id,
            data=data_str,
            config=resolved_props,
            context=context or {}
        )
        start_time = time.perf_counter()

        try:
            output: NodeOutput = await self.run(node_input)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            output_data = output.data
            if isinstance(output.data, str):
                try:
                    output_data = json.loads(output.data)
                except Exception:
                    pass

            return {
                "status": output.status,
                "data": output_data,
                "error_message": output.error_message,
                "error_code": output.error_code,
                "violations": output.violations,
                "metadata": output.metadata,
                "latency_ms": latency_ms
            }
        except Exception as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self.logger.error("isolated_node_test_failed", error=str(e))
            return {
                "status": "error",
                "error_message": str(e),
                "error_code": 500,
                "data": None,
                "latency_ms": latency_ms
            }


    def _resolve_dotted_path(self, dotted_path: str, obj: Any) -> Any:
        """Helper to navigate a dotted path (e.g. 'foo.bar') within a dict/object."""
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

    def _extract_list_values(self, expr: str, context: Dict[str, Any]) -> Optional[List[Any]]:
        """
        Extracts values from lists using json-path-like syntax (e.g. 'root[].date').
        """
        # Strip outer quotes if any
        path = expr.strip().strip("'\"")

        if '[]' not in path:
            return None

        left_part, right_part = path.split('[]', 1)
        left_part = left_part.strip()
        right_part = right_part.strip()

        # Get field name to extract from list items (e.g. "date")
        if right_part.startswith('.'):
            field_name = right_part[1:]
        else:
            field_name = right_part

        target_list = None

        # 1. Try to resolve left_part in context
        if left_part:
            target_list = self._resolve_dotted_path(left_part, context)
            if target_list is None:
                # Try context["input_data"] or context["data"]
                for candidate in ["input_data", "data"]:
                    cand_ctx = context.get(candidate)
                    if cand_ctx:
                        target_list = self._resolve_dotted_path(left_part, cand_ctx)
                        if target_list is not None:
                            break

        # 2. If target_list is still None, search standard roots
        if target_list is None or not isinstance(target_list, list):
            for candidate in ["input_data", "data"]:
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

        # 3. If target_list is still None, try check context directly
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

        # 4. Extract values from list items
        result = []
        for item in target_list:
            if isinstance(item, dict):
                if field_name:
                    val = self._resolve_dotted_path(field_name, item)
                    result.append(val)
                else:
                    result.append(item)
            else:
                result.append(item)
        return result

    def _resolve_single_expression(self, expr: str, context: Dict[str, Any]) -> Any:
        """
        Resolves a single template expression against the given context.
        """
        expr = expr.strip()
        lookup_expr = self._normalize_lookup_expression(expr)

        # Support root[].field or similar path extraction
        if '[]' in lookup_expr:
            resolved = self._extract_list_values(lookup_expr, context)
            if resolved is not None:
                return resolved

        # Try to resolve directly via dotted path lookup first
        # (e.g. input_data.text or user_question)
        if '.' in lookup_expr or lookup_expr in context:
            if not any(c in lookup_expr for c in ['"', "'", '(', ')']):
                resolved = self._resolve_dotted_path(lookup_expr, context)
                if resolved is not None:
                    return resolved

        # Otherwise, fall back to standard Jinja NativeTemplate render
        try:
            from jinja2.nativetypes import NativeTemplate
            from jinja2 import Undefined
            tpl = NativeTemplate(f"{{{{ {expr} }}}}")
            rendered = tpl.render(**context)
            if isinstance(rendered, Undefined):
                return None
            return rendered
        except Exception as e:
            self.logger.warning("jinja_expression_render_failed", trace_id=inp.trace_id, expr=expr, error=str(e))
            return None

    def _normalize_lookup_expression(self, expr: str) -> str:
        """
        Treat quoted field references like "stock_token" as stock_token.
        Literal strings still fall back to Jinja rendering if no matching field exists.
        """
        import re

        stripped = expr.strip()
        if len(stripped) < 2 or stripped[0] != stripped[-1] or stripped[0] not in {"'", '"'}:
            return stripped

        unquoted = stripped[1:-1].strip()
        if re.match(r"^[A-Za-z_]\w*(?:\[\])?(?:\.[A-Za-z_]\w*(?:\[\])?)*$", unquoted):
            return unquoted
        return stripped

    def transpose_resolved_value(self, val: Any) -> Any:
        """
        Transposes resolved list/dict template values if they refer to list attributes.
        """
        if isinstance(val, dict):
            # Check if this dict should be transposed
            db_keys = {"query", "query_type", "sql_query", "table_name"}
            if db_keys.intersection(val.keys()):
                return val

            # Check if we have values that are lists of the same length N > 0
            list_values = [v for v in val.values() if isinstance(v, list)]
            if list_values and len(set(len(x) for x in list_values)) == 1:
                n = len(list_values[0])
                if n > 0:
                    keys = list(val.keys())
                    transposed = []
                    for i in range(n):
                        item = {}
                        for k in keys:
                            v = val[k]
                            if isinstance(v, list) and len(v) == n:
                                item[k] = v[i]
                            else:
                                item[k] = v
                        transposed.append(item)
                    return transposed

        elif isinstance(val, list) and val:
            # Check if all elements are lists of the same length N > 0
            if all(isinstance(x, list) for x in val) and len(set(len(x) for x in val)) == 1:
                n = len(val[0])
                if n > 0:
                    return [list(x) for x in zip(*val)]

        return val

    def _resolve_variables(self, template: Any, data: Dict[str, Any]) -> Any:
        """
        Recursively resolves variables using simple {{ key }} replacement.
        """
        import re
        if isinstance(template, dict):
            return {k: self._resolve_variables(v, data) for k, v in template.items()}
        elif isinstance(template, list):
            if len(template) == 1:
                item_tpl = template[0]
                resolved_item = self._resolve_variables(item_tpl, data)
                if isinstance(resolved_item, dict):
                    db_keys = {"query", "query_type", "sql_query", "table_name"}
                    if not db_keys.intersection(resolved_item.keys()):
                        list_values = [v for v in resolved_item.values() if isinstance(v, list)]
                        if list_values and len(set(len(x) for x in list_values)) == 1:
                            n = len(list_values[0])
                            if n > 0:
                                keys = list(resolved_item.keys())
                                transposed = []
                                for i in range(n):
                                    item = {}
                                    for k in keys:
                                        v = resolved_item[k]
                                        if isinstance(v, list) and len(v) == n:
                                            item[k] = v[i]
                                        else:
                                            item[k] = v
                                    transposed.append(item)
                                return transposed
                elif isinstance(resolved_item, list) and resolved_item:
                    if all(isinstance(x, list) for x in resolved_item) and len(set(len(x) for x in resolved_item)) == 1:
                        n = len(resolved_item[0])
                        if n > 0:
                            return [list(x) for x in zip(*resolved_item)]
                return [resolved_item]
            else:
                return [self._resolve_variables(i, data) for i in template]
        elif isinstance(template, str) and self._has_template(template):
            # Match exactly {{key}}
            match = re.match(r"^\{\{\s*(.*?)\s*\}\}$", template.strip())
            if match:
                expr = match.group(1)
                resolved = self._resolve_single_expression(expr, data)
                if resolved is not None:
                    return resolved
                return template

            # Match mixed strings like "q={{key}}"
            pattern = re.compile(r"\{\{\s*(.*?)\s*\}\}")
            def replace_match(m):
                expr = m.group(1)
                resolved = self._resolve_single_expression(expr, data)
                if resolved is not None:
                    if isinstance(resolved, (list, dict)):
                        return json.dumps(resolved)
                    return str(resolved)
                return m.group(0)
            return pattern.sub(replace_match, template)
        return template

    def _has_template(self, val: Any) -> bool:
        """Recursively checks if a value contains a template string."""
        if isinstance(val, str):
            return "{{" in val and "}}" in val
        elif isinstance(val, dict):
            return any(self._has_template(v) for v in val.values())
        elif isinstance(val, list):
            return any(self._has_template(i) for i in val)
        return False

    def is_jinja_template(self, text: str) -> bool:
        """Check if string contains Jinja2 template syntax"""
        return "{{" in text and "}}" in text

    def _render_template_sets(self, template: List[str], render_context: List[Dict[str, Any]]) -> List[Set[Any]]:
        result = []
        for context in render_context:
            row_set: Set[Any] = set()
            
            for tmpl_str in template:
                if self.is_jinja_template(tmpl_str):
                    # Render with Jinja2
                    t = NativeTemplate(tmpl_str)
                    resolved = t.render(**context)
                    # Try to convert to proper type (e.g. "25" → 25)
                    try:
                        if resolved.isdigit():
                            resolved = int(resolved)
                        elif resolved.replace('.', '', 1).isdigit():
                            resolved = float(resolved)
                    except:
                        pass
                else:
                    # Static value - keep as is
                    resolved = tmpl_str
                
                row_set.add(resolved)
            
            result.append(row_set)
    
  
    def _resolve_jinja_templates(self, template: Any, render_context: Dict[str, Any]) -> Any:
        """
        Recursively resolves variables using Jinja2 NativeTemplate to preserve types.
        """
        if isinstance(template, dict):
            return {k: self._resolve_jinja_templates(v, render_context) for k, v in template.items()}
        elif isinstance(template, list):
            if isinstance(render_context, list):
                values = self._render_template_sets(template, render_context)
                return values
            return [self._resolve_jinja_templates(i, render_context) for i in template]
        elif isinstance(template, str) and "{{" in template and "}}" in template:
            import re
            match = re.match(r"^\{\{\s*(.*?)\s*\}\}$", template.strip())
            if match:
                expr = match.group(1)
                resolved = self._resolve_single_expression(expr, render_context)
                if resolved is not None:
                    return resolved
                return template

            # Match mixed strings
            pattern = re.compile(r"\{\{\s*(.*?)\s*\}\}")
            def replace_match(m):
                expr = m.group(1)
                resolved = self._resolve_single_expression(expr, render_context)
                if resolved is not None:
                    if isinstance(resolved, (list, dict)):
                        return json.dumps(resolved)
                    return str(resolved)
                return m.group(0)
            try:
                return pattern.sub(replace_match, template)
            except Exception as e:
                self.logger.warning("jinja_template_render_failed", template=template, error=str(e))
                return template
        return template



    async def validate_input_contract(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Validates if the input matches the defined input_contract.
        Checks mandatory fields and data types in the JSON body passed to the node.
        Returns a NodeOutput with failure status if validation fails, otherwise None.
        """
        self.logger.info("starting_validate_input_contract:checking_schema", trace_id=inp.trace_id, name= self.name)
        schema = inp.input_schema if getattr(inp, "input_schema", None) is not None else self.input_contract
        if not schema:
            self.logger.debug("No schema found", name= self.name,  trace_id=inp.trace_id,schema=schema)
            return None

        errors = validate_contract(schema, inp, self.name)

        if errors:
            self.logger.error(f"Ending validation of validate_input_contract",name= self.name,  trace_id=inp.trace_id,inp_data=inp.data,errors= "; ".join(errors))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="; ".join(errors),
                error_code=400,
                violations=["contract_violation"]
            )

        return None

    async def validate_output_contract(self, inp: NodeInput, output: NodeOutput) -> Optional[NodeOutput]:
        """
        Validates if the output matches the defined output_contract.
        Checks mandatory fields and data types in the JSON body returned by the node.
        """
        self.logger.info("starting validate_output_contract", trace_id=inp.trace_id, name=self.name)
        schema = inp.output_schema if getattr(inp, "output_schema", None) is not None else self.output_contract
        if not schema:
            self.logger.debug("No output schema found",  trace_id=inp.trace_id,name=self.name, schema=schema)
            return None

        from app.nodes.contracts import validate_contract

        errors = validate_contract(
            schema,
            output,
            self.name,
            context_nodes=inp.context.get("nodes", {})
        )

        if errors:
            self.logger.error(f"Ending validation of validate_output_contract", trace_id=inp.trace_id, name=self.name, out_data=output.data, errors="; ".join(errors))
            output.status = "failure"
            output.error_message = "; ".join(errors)
            output.error_code = 400
            if "contract_violation" not in output.violations:
                output.violations.append("contract_violation")

        return None

    # -------------------------------------------------------------------------
    # File-field resolution
    # -------------------------------------------------------------------------

    def _iter_contract_rules(self, inp: NodeInput):
        """
        Yield each rule dict from the effective input contract.

        Supports both formats:
          • Array-of-rules  (contract has a 'rules' list)
          • Dict keyed by field name (legacy / inline contract)
        """
        schema = inp.input_schema if getattr(inp, "input_schema", None) else self.input_contract
        if not schema:
            return

        # Array-of-rules format: {"rules": [{"field_name": …, "field_type": …}, …]}
        rules = schema.get("rules") if isinstance(schema, dict) else None
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict):
                    yield rule
            return

        # Dict-keyed format: {"file_path": {"type": "file", …}, …}
        if isinstance(schema, dict):
            for fname, fdef in schema.items():
                if fname in {"type", "required", "additionalProperties"}:
                    continue
                if isinstance(fdef, dict):
                    rule = dict(fdef)
                    rule.setdefault("field_name", fname)
                    yield rule

    def _resolve_file_fields(self, inp: NodeInput) -> None:
        """
        Scan the effective input contract for rules whose ``field_type`` is
        ``"file"`` (or any of its aliases: ``pdf``, ``doc``, ``docx``,
        ``image``, ``png``, ``jpg``, ``jpeg``).

        For each matching rule the method:

        1. Looks up ``<field_name>.path`` in the current ``inp.data`` dict.
        2. If found and non-empty, reads the file with
           :func:`app.utils.file_utils.load_file_bytes`.
        3. Injects a structured sub-dict back into ``inp.data``:

           .. code-block:: json

               {
                   "path": "/abs/path/to/file.pdf",
                   "type": ".pdf",
                   "content_base64": "<base64-encoded bytes>"
               }

        The field is **optional** — if no path is provided the key is left
        untouched and execution continues normally.

        On ``FileNotFoundError``, ``PermissionError``, or ``OSError`` the
        method logs the error and raises so the caller can return a
        structured ``NodeOutput(status='failure', …)``.
        """
        _FILE_TYPES = {"file", "pdf", "doc", "docx", "image", "png", "jpg", "jpeg"}

        # Parse current inp.data into a mutable dict
        try:
            data_obj = json.loads(inp.data) if inp.data else {}
        except Exception:
            data_obj = {}

        if not isinstance(data_obj, dict):
            return  # non-dict payload — nothing to inject

        # Unwrap one "data" envelope if present
        payload = data_obj.get("data", data_obj) if "data" in data_obj else data_obj
        if not isinstance(payload, dict):
            return

        changed = False
        for rule in self._iter_contract_rules(inp):
            ft = str(rule.get("field_type") or rule.get("type") or "").lower()
            if ft not in _FILE_TYPES:
                continue

            # The contract field name is the *top-level* key (before any dot)
            field_name_full = str(rule.get("field_name") or rule.get("name") or "").strip()
            # e.g. "file_path.type" → top key is "file_path"
            top_key = field_name_full.split(".")[0] if "." in field_name_full else field_name_full
            if not top_key:
                continue

            # Locate the file sub-object (e.g. payload["file_path"])
            file_obj = payload.get(top_key)
            if not isinstance(file_obj, dict):
                # Also accept a bare string treated as the path directly
                if isinstance(file_obj, str) and file_obj.strip():
                    file_obj = {"path": file_obj.strip(), "type": ""}
                else:
                    continue  # no path provided — skip gracefully

            file_path = str(file_obj.get("path") or "").strip()
            if not file_path:
                continue  # optional field with no path — skip

            self.logger.info(
                "file_field_resolving",
                field=top_key,
                path=file_path,
                trace_id=inp.trace_id,
            )

            # Read file — propagate OS errors to caller for structured failure
            raw_bytes, detected_ext = load_file_bytes(file_path)

            mime_hint = str(file_obj.get("type") or detected_ext or "").lower()

            # Attempt text extraction for text-based workflows (PDF, DOCX, TXT, MD, etc.)
            extracted_text = ""
            try:
                extracted_text = extract_document_text(file_path, filename_or_ext=mime_hint or detected_ext)
            except Exception as exc:
                self.logger.warning("file_field_text_extraction_failed", field=top_key, path=file_path, error=str(exc))

            b64_content = base64.b64encode(raw_bytes).decode("utf-8")

            # Inject enriched sub-object back into payload containing both binary & text formats
            payload[top_key] = {
                "path": file_path,
                "type": mime_hint or detected_ext,
                #"content_base64": b64_content,
                "content_text": extracted_text,
                "text": extracted_text,
                "content": extracted_text if (extracted_text and extracted_text.strip()) else b64_content,
            }
            changed = True
            self.logger.info(
                "file_field_resolved",
                field=top_key,
                #bytes_read=len(raw_bytes),
                text_length=len(extracted_text),
                ext=detected_ext,
                trace_id=inp.trace_id,
            )

        if changed:
            # Write enriched payload back into inp.data preserving the envelope
            if "data" in data_obj:
                data_obj["data"] = payload
                inp.data = json.dumps(data_obj)
            else:
                inp.data = json.dumps(payload)

    def get_input_data(self, inp: NodeInput) -> Any:
        """
        Extracts the inner value of the 'data' parameter from the incoming payload.
        Handles both wrapped JSON structures and raw inputs gracefully.
        """
        if not inp.data:
            return None
        try:
            parsed = json.loads(inp.data)
            if isinstance(parsed, dict) and "data" in parsed:
                return parsed["data"]
            return parsed
        except Exception:
            return inp.data

    def set_output_data(self, inp: NodeInput, new_data: Any) -> str:
        """
        Wraps the output value inside the 'data' parameter key, preserving
        any other top-level keys in the envelope if they exist.
        """
        try:
            parsed = json.loads(inp.data)
            if isinstance(parsed, dict) and "data" in parsed:
                parsed["data"] = new_data
                return json.dumps(parsed)
        except Exception:
            pass
        return json.dumps({"data": new_data})

    def transform_strings(self, val: Any, func) -> Any:
        """
        Recursively traverses a JSON-compatible structure (dict, list, string)
        and transforms all string values using the provided function.
        """
        if isinstance(val, str):
            return func(val)
        elif isinstance(val, dict):
            return {k: self.transform_strings(v, func) for k, v in val.items()}
        elif isinstance(val, list):
            return [self.transform_strings(item, func) for item in val]
        return val

    def collect_strings(self, val: Any) -> List[str]:
        """
        Recursively traverses a JSON-compatible structure (dict, list, string)
        and collects all string values in a flat list.
        """
        strings = []
        def _collect(v):
            if isinstance(v, str):
                strings.append(v)
            elif isinstance(v, dict):
                for val_item in v.values():
                    _collect(val_item)
            elif isinstance(v, list):
                for item in v:
                    _collect(item)
        _collect(val)
        return strings

    @abc.abstractmethod
    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        return None

    @abc.abstractmethod
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        The core logic implementation for the node.
        This is the single abstract method to be implemented by child classes.
        """


    async def _resolve_source_properties(self, inp: NodeInput) -> None:
        """
        Generic resolution for any property of type 'source' or having a 'source' API URL defined.
        Calls the configured API endpoint for selected property values and merges all returned JSON data key-values into inp.config.
        """
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:

            nodes_result = await session.execute(select(NodeDB).where(NodeDB.name == self.name))
            result = nodes_result.scalars().first()
            if not result:
                return  
            user_props = result.user_properties if isinstance(result.user_properties, list) else (list(result.user_properties.values()) if isinstance(result.user_properties, dict) else [])
            system_props = result.system_properties if isinstance(result.system_properties, list) else (list(result.system_properties.values()) if isinstance(result.system_properties, dict) else [])
            db_node_properties = user_props + system_props

            source_schemas = [
                s for s in db_node_properties
                if isinstance(s, dict) and (s.get("source") or s.get("type") == "source")
            ]   

            if not source_schemas:
                return

            for schema in source_schemas:
                prop_key = schema.get("key")
                source_url = schema.get("source")
                if not prop_key or not source_url or not isinstance(source_url, str):
                    continue

                val = inp.config.get(prop_key)
                if val is None or val == "":
                    continue

                if not (source_url.startswith("/") or source_url.startswith("http")):
                    continue

                # ==============================================================
                # BLOCK COMMENT: UPDATED SOURCE FIELD RESOLUTION
                # Appends configured fields query param and filters sensitive fields
                # ==============================================================
                req_fields = schema.get("fields") or schema.get("required_fields")
                full_url = source_url
                if req_fields and isinstance(req_fields, list):
                    param_str = ",".join(str(f) for f in req_fields)
                    delimiter = "&" if "?" in full_url else "?"
                    full_url = f"{full_url}{delimiter}fields={param_str}"

                try:
                    import os
                    import httpx

                    backend_url = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:8000")
                    target_url = full_url if full_url.startswith("http") else f"{backend_url.rstrip('/')}{full_url if full_url.startswith('/') else '/' + full_url}"

                    async with httpx.AsyncClient(timeout=5.0) as client:
                        res = await client.get(target_url)
                        if res.status_code != 200:
                            continue

                        json_data = res.json()
                    target_item = None

                    if isinstance(json_data, dict):
                        items = (
                            json_data.get("items")
                            or json_data.get("profiles")
                            or json_data.get("bases")
                            or json_data.get("results")
                            or json_data.get("data")
                        )
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict) and str(item.get("id") or item.get("key") or item.get("value") or item.get("name")) == str(val):
                                    target_item = item
                                    break
                        else:
                            target_item = json_data
                    elif isinstance(json_data, list):
                        for item in json_data:
                            if isinstance(item, dict) and str(item.get("id") or item.get("key") or item.get("value") or item.get("name")) == str(val):
                                target_item = item
                                break

                    # Store returned data fields into inp.config
                    if isinstance(target_item, dict):
                        model_type = str(inp.config.get("model_type") or "generation").lower()
                        settings = target_item.get("settings")
                        sensitive_keys = {"api_key", "secret", "password", "auth_token"}
                        allowed_keys = set(req_fields) if (req_fields and isinstance(req_fields, list)) else None

                        if isinstance(settings, dict):
                            sec = (
                                settings.get(model_type)
                                or settings.get("generation")
                                or settings.get("search")
                                or settings.get("embedding")
                            )
                            if isinstance(sec, dict):
                                if sec.get("url") and not inp.config.get("llm_endpoint"):
                                    inp.config["llm_endpoint"] = sec.get("url")
                                    inp.config["url"] = sec.get("url")
                                if sec.get("model") and not inp.config.get("model"):
                                    inp.config["model"] = sec.get("model")
                                if sec.get("api_key") and not inp.config.get("api_key") and (not allowed_keys or "api_key" in allowed_keys):
                                    inp.config["api_key"] = sec.get("api_key")
                                if sec.get("system_prompt") and not inp.config.get("system_prompt"):
                                    inp.config["system_prompt"] = sec.get("system_prompt")
                                if sec.get("temperature") is not None and inp.config.get("temperature") is None:
                                    inp.config["temperature"] = sec.get("temperature")

                        if (target_item.get("url") or target_item.get("endpoint")) and not inp.config.get("llm_endpoint"):
                            endpoint = target_item.get("url") or target_item.get("endpoint")
                            inp.config["llm_endpoint"] = endpoint
                            inp.config["url"] = endpoint
                        if target_item.get("model") and not inp.config.get("model"):
                            inp.config["model"] = target_item.get("model")
                        if target_item.get("api_key") and not inp.config.get("api_key") and (not allowed_keys or "api_key" in allowed_keys):
                            inp.config["api_key"] = target_item.get("api_key")
                        if target_item.get("system_prompt") and not inp.config.get("system_prompt"):
                            inp.config["system_prompt"] = target_item.get("system_prompt")

                        for k, v in target_item.items():
                            if allowed_keys and k not in allowed_keys and k not in ("llm_endpoint", "url", "model", "model_name"):
                                continue
                            if k.lower() in sensitive_keys:
                                continue
                            if k not in inp.config or inp.config[k] is None or inp.config[k] == "":
                                inp.config[k] = v
                except Exception as exc:
                    self.logger.warning("source_api_resolution_failed", prop_key=prop_key, source_url=source_url, error=str(exc))

    async def run(self, inp: NodeInput) -> NodeOutput:
        """
        The standardized execution lifecycle for every node in the system.
        Executes:
        1. Context Setup: Enriches context with execution tracing data.
        2. Config Setup: Merges static properties with runtime input configs.
        3. Execution: Runs the core business logic (execute).
        4. Observability: Captures latency, start/end times, and status.
        5. Error Handling: Gracefully catches exceptions and returns a failure NodeOutput.

        Returns:
            NodeOutput: The standardized result containing content, status, and metadata.
        """
        self.logger.info("node_run_started", name = self.name, trace_id=inp.trace_id)
        start_ts = time.time()
        try:
            # Store trace_id in context for observability
            if inp.context is None:
                inp.context = {}

            # 0. Resolve properties: (Registry Defaults enriched by init) < Workflow Config
            inp.config = {**self.properties, **inp.config}
            # await self._resolve_source_properties(inp)

            # 0.05 Parse input_data
            input_data = {}
            if inp.data:
                try:
                    input_data = json.loads(inp.data)
                except Exception:
                    input_data = inp.data

            # Extract the actual input values inside "data" key if present
            if isinstance(input_data, dict):
                input_data_data = input_data.get("data") if ("data" in input_data and "query_type" not in input_data) else input_data
            else:
                input_data_data = input_data

            # 0.06 Get mappings directly from config
            mapping_config = inp.config.get("mapping_template") or inp.config.get("input_mappings")
            if mapping_config:
                if isinstance(mapping_config, str):
                    try:
                        mapping_config = json.loads(mapping_config)
                    except Exception:
                        pass

            if isinstance(mapping_config, dict):
                mapping_config = {k: v for k, v in mapping_config.items() if not k.startswith('_')}

            # 0.08 Build render context and resolve templates
            try:
                render_context = {}
                if isinstance(inp.context, dict):
                    render_context.update(inp.context)
                if isinstance(input_data_data, dict):
                    render_context.update(input_data_data)

                render_context["data"] = input_data_data
                render_context["input_data"] = input_data_data
                if inp.context and isinstance(inp.context, dict):
                    render_context["nodes"] = inp.context.get("nodes", {})
                    render_context["user_data"] = inp.context.get("user_data", {})

                self.logger.debug("running_node:resolve_jinja_template", render_context=render_context, trace_id=inp.trace_id)
                
                # Resolve mapping_config if present (uses mapping strictly as data source), otherwise resolve templates in input_data_data directly
                if mapping_config:
                    resolved_data = self._resolve_jinja_templates(mapping_config, render_context)
                else:
                    resolved_data = self._resolve_jinja_templates(input_data_data, render_context)

                # Save resolved data back to inp.data
                if isinstance(resolved_data, (dict, list)):
                    inp.data = json.dumps(resolved_data)
                elif resolved_data is not None:
                    inp.data = str(resolved_data)
                else:
                    inp.data = ""

                # find and replace all templates in properties / config
                resolved_config = self._resolve_jinja_templates(inp.config, render_context)
                inp.config = resolved_config
            except Exception as e:
                self.logger.error("failed_to_resolve_mapping_templates", trace_id=inp.trace_id, error=str(e))

            # 0.1 Input Contract Validation
            # 0.09 Resolve file fields declared as field_type='file' in the contract
            try:
                self._resolve_file_fields(inp)
            except FileNotFoundError as exc:
                self.logger.error("file_field_not_found", error=str(exc), trace_id=inp.trace_id)
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_message=(
                        f"File not found: {exc}. "
                        "Verify the path in the file field points to a server-accessible file."
                    ),
                )
            except PermissionError as exc:
                self.logger.error("file_field_permission_denied", error=str(exc), trace_id=inp.trace_id)
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_message=(
                        f"Permission denied: {exc}. "
                        "The server process cannot read this file."
                    ),
                )
            except OSError as exc:
                self.logger.error("file_field_os_error", error=str(exc), trace_id=inp.trace_id)
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_message=f"File I/O error: {exc}",
                )

            # 0.1 Input Contract Validation
            contract_output = await self.validate_input_contract(inp)
            if contract_output:
                return contract_output

            validation_output = await self.validate_input(inp)
            if validation_output:
                return validation_output

            # 2. Execution logic
            self.logger.info(f"Node execution started {self.name}",trace_id=inp.trace_id)
            output = await self.execute(inp)

            end_ts = time.time()
            self.logger.info(f"Node execution completed {self.name}",trace_id=inp.trace_id)
            # Enrich output with tracking data
            output.start_time = start_ts
            output.end_time = end_ts
            output.latency_ms = round((end_ts - start_ts) * 1000, 2)

            # # 3. Apply Output Envelope if execution was successful
            # if not output.error_message and not output.violations:
            #     output.output_data = self.apply_output_envelope(output.output_data, inp)

            # Output Contract Validation
            if not output.error_message and not output.violations:
                await self.validate_output_contract(inp, output)

            output.status = "failure" if output.error_message or output.violations else "success"

            self.logger.info(
                "node_run_completed",
                name=self.name,
                status=output.status, function_name=__name__,
                latency_ms=output.latency_ms,
                output=output.status, trace_id=inp.trace_id
            )
            return output

        except Exception as e:
            end_ts = time.time()
            self.logger.error(
                "node_run_exception",
                name=self.name,
                error=str(e),
                trace_id=inp.trace_id,
                input=inp.model_dump()
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                error_code=500,
                status="failure",
                error_message=str(e),
                start_time=start_ts,
                end_time=end_ts,
                latency_ms=round((end_ts - start_ts) * 1000, 2)
            )

class TriggerNode(BaseNode, abc.ABC):
    """
    A specialized node type that sits at the start of a workflow graph.

    Unlike standard nodes, TriggerNodes:
    1. Are "activated" on system startup to listen for external events.
    2. Can initiate the WorkflowExecutor when an event (Webhook/Timer/Email) occurs.
    3. Manage an internal registry of workflow configurations they are responsible for.
    """
    node_type: str = "TRIGGER"

    async def init(self) -> None:
        """Triggers should still load their properties from the database."""
        self.logger.info(
                        "Trigger node init started",
                        name=self.name,
                    )
        await super().init()
        self.logger.info(
                        "Trigger node init ended",
                        name=self.name,
                    )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Default trigger execution just passes the input payload through."""
        self.logger.info(
                        "Trigger node execution  started",
                        name=self.name,
                        trace_id=inp.trace_id,
                    )
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Triggers can choose to implement validation if needed, but by default they don't block execution
        return None

    # Internal registry to map specific node instances (by agent_node_id)
    # to their parent workflow configurations.
    _workflows: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]) -> None:
        """
        Registers a specific workflow instance to this trigger agent.

        This method is critical for triggers (like Webhooks or Schedulers) to know
        which workflow graph to execute when an external event occurs.

        Args:
            agent_node_id: The unique ID of the trigger node within the specific workflow.
            workflow_config: The full JSON definition of the workflow to be executed.
        """
        self.logger.info(
                        "Trigger node  activation started",
                        name=self.name,
                    )
        self._workflows[agent_node_id] = workflow_config

        # Global node properties are loaded in init()
        # Instance properties should be resolved using _get_node_config() when needed
        self.logger.debug("workflow_registered_to_trigger",
                          name=self.name,
                          workflow_id=workflow_config.get("id"))

    async def execute_dynamic_agent(self, agent_node_id: str, payload: Any, trace_id: Optional[str] = None):
        """
        Unified implementation for all triggers to initiate workflow execution.
        This method builds the langgraph flow via the executor and starts it.
        It retrieves the workflow_config from the internal _workflows registry.
        """
        from app.workflows.executor import WorkflowExecutor
        # Generate a trace ID if not provided, prefixed by node name for observability
        t_id = trace_id or f"{self.name}-{int(time.time())}"

        self.logger.debug("execute_dynamic_agent started",
                          name=self.name, trace_id=t_id,
                         workflow_id=agent_node_id)

        # Retrieve the workflow config for this specific agent_node_id
        workflow_config = self._workflows.get(agent_node_id)
        if not workflow_config:
            self.logger.warning("dynamic_agent_execution_failed_no_workflow_config", agent_node_id=agent_node_id, trace_id=t_id)
            return None

        # Trigger the workflow execution via the central executor logic
        try:
            self.logger.debug("WorkflowExecutor started", name=self.name, trace_id=t_id, workflow_id=workflow_config.get("id"))

            executor = WorkflowExecutor(workflow_config)

            # Ensure payload is wrapped under the "data" key to conform to standard input envelope
            wrapped_payload = None
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict) and "data" in parsed:
                        wrapped_payload = parsed
                    else:
                        wrapped_payload = {"data": parsed}
                except Exception:
                    wrapped_payload = {"data": payload}
            elif isinstance(payload, dict):
                if "data" in payload:
                    wrapped_payload = payload
                else:
                    wrapped_payload = {"data": payload}
            else:
                wrapped_payload = {"data": payload}

            content = json.dumps(wrapped_payload)
            self.logger.debug("WorkflowExecutor ended",
                          name=self.name,trace_id=t_id,
                          workflow_id=workflow_config.get("id"))

            return await executor.execute_async(content, t_id)
        except Exception as e:
            self.logger.error("dynamic_agent_execution_crashed",name=self.name, error=str(e), trace_id=t_id)
            return None
