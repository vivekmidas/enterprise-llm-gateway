import asyncio
import importlib
import inspect
import json
import os
import pkgutil
from pathlib import Path
import structlog
from typing import Dict, List, Optional, Type, Any
from pydantic import PrivateAttr
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput

class LazyPluginNode(BaseNode):
    """
    BLOCK COMMENT: Proxy node representing an uninstantiated plugin.
    Epic: Independent Custom Node Publishing & Execution Robustness (Phase 2)
    Defers importing the plugin script and external packages until the first execution.
    This guarantees zero plugin package imports at server startup.
    """
    user_properties: Any = None
    system_properties: Any = None

    _plugin_dir: str = PrivateAttr()
    _script_path: str = PrivateAttr()
    _class_name: str = PrivateAttr()
    _module_name: str = PrivateAttr()
    _real_instance: Optional[BaseNode] = PrivateAttr(default=None)
    _load_lock: Any = PrivateAttr(default=None)
    _raw_user_properties: Any = PrivateAttr(default=None)
    _raw_system_properties: Any = PrivateAttr(default=None)

    def __init__(
        self,
        plugin_dir: str,
        script_path: str,
        class_name: str,
        module_name: str,
        **data
    ):
        super().__init__(**data)
        self._plugin_dir = plugin_dir
        self._script_path = script_path
        self._class_name = class_name
        self._module_name = module_name
        self._real_instance = None
        self._load_lock = asyncio.Lock()
        self._raw_user_properties = data.get("user_properties", [])
        self._raw_system_properties = data.get("system_properties", [])

    async def init(self) -> None:
        """Lightweight init populating properties/contracts without importing plugin code."""
        await super().init()

    async def _ensure_loaded(self) -> BaseNode:
        """Dynamically imports the plugin script and instantiates the underlying node class on first use."""
        if self._real_instance is not None:
            return self._real_instance

        if self._load_lock is None:
            self._load_lock = asyncio.Lock()

        async with self._load_lock:
            if self._real_instance is not None:
                return self._real_instance

            import sys
            import importlib.util

            if self._plugin_dir not in sys.path:
                sys.path.append(self._plugin_dir)
            vendor_dir = os.path.join(self._plugin_dir, "vendor")
            if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
                sys.path.append(vendor_dir)

            spec = importlib.util.spec_from_file_location(self._module_name, self._script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for plugin: {self._script_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[self._module_name] = module
            spec.loader.exec_module(module)

            cls_obj = getattr(module, self._class_name, None)
            if not cls_obj or not issubclass(cls_obj, BaseNode) or inspect.isabstract(cls_obj):
                raise TypeError(
                    f"Invalid node class '{self._class_name}' in plugin '{self._script_path}'"
                )

            instance = cls_obj()
            instance.customer_id = self.customer_id
            instance.name = self.name

            # Transfer properties and contracts configured in proxy/DB
            if hasattr(self, "properties") and self.properties:
                instance.properties = dict(self.properties)
            if hasattr(self, "user_properties") and self.user_properties:
                instance.user_properties = self.user_properties
            if hasattr(self, "system_properties") and self.system_properties:
                instance.system_properties = self.system_properties
            if hasattr(self, "input_contract") and self.input_contract:
                instance.input_contract = self.input_contract
            if hasattr(self, "output_contract") and self.output_contract:
                instance.output_contract = self.output_contract

            await instance.init()
            self._real_instance = instance
            return self._real_instance

    async def execute(self, inp: NodeInput) -> NodeOutput:
        real_node = await self._ensure_loaded()
        return await real_node.execute(inp)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        real_node = await self._ensure_loaded()
        return await real_node.validate_input(inp)

    async def test(
        self,
        test_input: Any,
        override_properties: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        real_node = await self._ensure_loaded()
        return await real_node.test(
            test_input=test_input,
            override_properties=override_properties,
            context=context
        )

    def get_resolved_properties(
        self,
        instance_overrides: Optional[Dict[str, Any]] = None,
        tenant_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self._real_instance is not None:
            return self._real_instance.get_resolved_properties(
                instance_overrides=instance_overrides,
                tenant_overrides=tenant_overrides
            )
        return super().get_resolved_properties(
            instance_overrides=instance_overrides,
            tenant_overrides=tenant_overrides
        )

class NodesRegistry: 
    """
    Registry for managing and dynamically discovering nodes.
    """
    _nodes: Dict[str, BaseNode] = {}
    logger = structlog.get_logger("NodesRegistry")

    @staticmethod
    def _parse_version_tuple(version_str: Optional[str]) -> tuple:
        """
        Parses a version string (e.g. '1.2.3') into a comparable tuple of integers.
        Non-numeric suffixes are stripped or compared safely.
        """
        import re
        if not version_str:
            return (0, 0, 0)
        parts = re.findall(r"\d+", str(version_str))
        if not parts:
            return (0, 0, 0)
        nums = tuple(int(p) for p in parts)
        if len(nums) < 3:
            nums = nums + (0,) * (3 - len(nums))
        return nums

    @classmethod
    def _is_newer_version(cls, new_version: Optional[str], db_version: Optional[str]) -> bool:
        """
        Returns True strictly when `new_version` is greater than `db_version`.
        """
        if not new_version:
            return False
        if not db_version:
            return True
        return cls._parse_version_tuple(new_version) > cls._parse_version_tuple(db_version)

    @classmethod
    async def register(cls, agent: BaseNode):
        """Registers an instantiated node."""
        if not agent.name or agent.name == "base_node":
            cls.logger.debug("skip_registration_base_agent", agent_name=agent.name)
            return

        agent.node_type = (agent.node_type or "NODE").strip().upper()
        if agent.node_type == "DEFAULT":
            agent.node_type = "NODE"

        # Enrich node with external properties (from JSON) if they exist
        cls._enrich_node_from_storage(agent)
        await agent.init()

        cls._nodes[agent.name] = agent
        cls.logger.info("node_registered", name=agent.name, category=agent.category, version=agent.version)

    @classmethod
    def _enrich_node_from_storage(cls, node: BaseNode):
        """
        Attempts to load default properties and schema overrides from a JSON file.
        """
        base_dir = Path(__file__).resolve().parent.parent.parent
        config_dir = base_dir / "data" / "nodes"
        config_file = config_dir / f"{node.name}.json"

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    external_data = json.load(f)
                    if "properties" in external_data:
                        node.properties.update(external_data["properties"])
                    if "user_properties" in external_data:
                        merged_u = node.merge_property_definitions(node._definition_user_properties, external_data["user_properties"])
                        node._definition_user_properties = merged_u
                        if isinstance(node.user_properties, list) or not node.user_properties:
                            node.user_properties = merged_u
                    if "system_properties" in external_data:
                        merged_s = node.merge_property_definitions(node._definition_system_properties, external_data["system_properties"])
                        node._definition_system_properties = merged_s
                        if isinstance(node.system_properties, list) or not node.system_properties:
                            node.system_properties = merged_s
                    if "input_contract" in external_data:
                        node.input_contract = node.merge_contract_definitions(node.input_contract, external_data["input_contract"])
                        node._definition_input_contract = dict(node.input_contract)
                    if "output_contract" in external_data:
                        node.output_contract = node.merge_contract_definitions(node.output_contract, external_data["output_contract"])
                        node._definition_output_contract = dict(node.output_contract)
                    cls.logger.debug("node_properties_enriched", name=node.name)
            except Exception as e:
                cls.logger.error("failed_to_enrich_node", name=node.name, error=str(e))

    @classmethod
    def get_node(cls, name: str) -> Optional[BaseNode]:
        """Retrieves a node by its unique name."""
        cls.logger.debug("get_node_request", name=name)
        node = cls._nodes.get(name)
        if node:
            cls.logger.debug("get_node_hit", name=name)
        else:
            cls.logger.debug("get_node_miss", name=name)
        return node

    @classmethod
    def list_nodes(cls) -> List[BaseNode]:
        """Returns a list of all registered nodes."""
        cls.logger.debug("list_nodes_request", count=len(cls._nodes))
        return list(cls._nodes.values())

    @classmethod
    async def node_auto_discover(cls):
        """
        Dynamically discovers node definitions in built-in and plugin directories.
        """
        cls.logger.info("node_auto_discover_started")
        # 1. Discover built-in nodes
        try:
            import app.nodes.built_in as built_in_pkg
            package_name = built_in_pkg.__name__
            # Ensure we scan all paths in the package as a single list for robust recursion
            package_paths = list(getattr(built_in_pkg, "__path__", []))
            if not package_paths and hasattr(built_in_pkg, "__file__") and built_in_pkg.__file__:
                package_paths = [os.path.dirname(built_in_pkg.__file__)]
            await cls._scan_package(package_paths, package_name)
        except ImportError:
            cls.logger.warning("built_in_agents_package_not_found")

        # 2. Discover plugin agents from 'plugins/nodes/system' folder
        plugins_dir = os.path.join(os.getcwd(), "plugins", "nodes", "system")
        if not os.path.exists(plugins_dir):
            base_backend_dir = Path(__file__).resolve().parent.parent.parent
            candidate = base_backend_dir / "plugins" / "nodes" / "system"
            if candidate.exists():
                plugins_dir = str(candidate)
        await cls._load_plugins_from_directory(plugins_dir, customer_id=0)

        # 3. Discover customer-specific plugins from CustomerDB paths
        await cls._load_customer_custom_plugins()

        # Log the "output" of the discovery process
        cls.logger.info(
            "node_auto_discover_completed", 
            nodes_count=len(cls._nodes), 
            registered_nodes=list(cls._nodes.keys())
        )

    @classmethod
    async def sync_with_db(cls):
        """
        Syncs all registered nodes into the database using canonical `add_node_to_db`.
        """
        cls.logger.info("syncing_registry_with_db")
        for node in cls._nodes.values():
            await cls.add_node_to_db(node)
        cls.logger.info("nodes_synced_with_db", count=len(cls._nodes))

    @classmethod
    async def _scan_package(cls, package_paths: List[str], prefix: str):
        """Walks through a package and its sub-packages to find agents."""
        cls.logger.info("scanning_package", paths=package_paths, prefix=prefix)

        # 1. Load the root package itself first (to find agents in __init__.py)
        if prefix:
            await cls._load_module(prefix)

        # 2. Recursively find and load all sub-modules
        for _, module_name, ispkg in pkgutil.walk_packages(package_paths, prefix=f"{prefix}." if prefix else ""):
            cls.logger.debug("found_module", module=module_name, is_package=ispkg)
            if ispkg:
                cls.logger.info("scanning_directory", module=module_name)
            await cls._load_module(module_name)

    @classmethod
    async def _scan_directory(cls, directory: str):
        """Scans a flat directory for python files containing agents."""
        cls.logger.debug("scanning_directory", directory=directory)
        for filename in os.listdir(directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                await cls._load_module(module_name)

    @classmethod
    async def _load_module(cls, module_name: str):
        """Loads a module and registers any BaseNode subclasses found within."""
        cls.logger.debug("loading_module", module=module_name)
        try:
            # Import the module. 
            # We avoid importlib.reload() as it can break class identity checks (issubclass)
            # by creating fresh class objects that differ from the ones in the registry's memory.
            module = importlib.import_module(module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ != module.__name__:
                    continue
                if issubclass(obj, BaseNode) and obj is not BaseNode and not inspect.isabstract(obj):
                    cls.logger.info("found_node_class", class_name=obj.__name__, module=module_name)
                    try:
                        instance = obj()
                        cls._enrich_node_from_storage(instance)
                        await cls.add_node_to_db(instance)
                        await cls.register(instance)
                    except Exception as e:
                        cls.logger.error("node_instantiation_failed", node=obj.__name__, error=str(e))
        except Exception as e:
            cls.logger.error("node_module_load_failed", module=module_name, error=str(e))

    # ==========================================================================
    # BLOCK COMMENT: NODE DB INITIALIZATION & SEMANTIC VERSION UPGRADE
    # Reference: EPIC-NODE-BASE-001 / STORY-NODE-INIT-001
    # Description:
    #     Initializes or updates the node row in `nodes` table (NodeDB) using
    #     the 12 standardized base properties under two conditions:
    #       a) Node `name` does not exist in `nodes` table.
    #       b) Node definition has a newer semantic version (`node.version > db_node.version`).
    #     Normalizes `node_type` to uppercase (default "NODE") and persists `db_node.version`.
    # ==========================================================================
    @classmethod
    async def add_node_to_db(cls, node: BaseNode):
        """
        Saves the node's definition and metadata to the database when:
          a) No node with `node.name` exists in `nodes` table, OR
          b) The node definition version is strictly newer (`node.version > db_node.version`).
        """
        from app.core.database import AsyncSessionLocal
        from app.models.db_models import NodeDB, CustomerNodeDB
        from sqlalchemy import select

        if not node.name or node.name == "base_node":
            return

        cls.logger.info("adding_node_to_db_started", node_name=node.name, version=node.version)

        defn = node.get_node_definition() if hasattr(node, "get_node_definition") else {}

        # Extract merged unmutated schema properties (respecting direct list assignments on node)
        if isinstance(node, LazyPluginNode):
            user_props_code = node._raw_user_properties or defn.get("user_properties") or []
            system_props_code = node._raw_system_properties or defn.get("system_properties") or []
        else:
            if isinstance(node.user_properties, list) and node.user_properties:
                user_props_code = node.user_properties
            else:
                user_props_code = defn.get("user_properties") if defn.get("user_properties") is not None else []
            if isinstance(node.system_properties, list) and node.system_properties:
                system_props_code = node.system_properties
            else:
                system_props_code = defn.get("system_properties") if defn.get("system_properties") is not None else []

        # Map node category to the corresponding Category ID
        node_category = str(getattr(node, "category", "") or "Node")
        category_id = "1"
        if node_category.lower() in ["guardrails", "safety guardrails"]:
            category_id = "2"
        elif node_category.lower() in ["external systems", "external"]:
            category_id = "3"
        elif node_category.lower() in ["data operations", "transform"]:
            category_id = "4"
        elif node_category.lower() in ["databases", "database"]:
            category_id = "5"
        elif node_category.lower() in ["triggers", "trigger"]:
            category_id = "6"
        else:
            category_id = "1"

        raw_node_type = (node.node_type or "NODE").strip().upper()
        if raw_node_type == "DEFAULT" or not raw_node_type:
            raw_node_type = "NODE"

        cust_id = getattr(node, "customer_id", None)
        db_cust_id = None if cust_id == 0 else cust_id

        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(NodeDB).where(NodeDB.name == node.name)
                result = await session.execute(stmt)
                db_node = result.scalars().first()

                if not db_node:
                    # Condition (a): Node name does not exist in nodes table
                    cls.logger.info("registering_new_node_to_db", name=node.name, version=node.version)
                    new_db_node = NodeDB(
                        name=node.name,
                        label=node.label,
                        node_type=raw_node_type,
                        description=node.description,
                        version=node.version,
                        category=category_id,
                        group=node.group,
                        icon=node.icon or "bot",
                        color=node.color or "#5E0CEC",
                        badge=node.badge,
                        sub_label=node.sub_label,
                        user_properties=user_props_code,
                        system_properties=system_props_code,
                        input_contract=node.input_contract if node.input_contract is not None else {},
                        output_contract=node.output_contract if node.output_contract is not None else {},
                        customer_id=db_cust_id
                    )
                    session.add(new_db_node)
                elif cls._is_newer_version(node.version, db_node.version):
                    # Condition (b): New version of the node definition (new_version > db_version)
                    cls.logger.info(
                        "overwriting_existing_node_in_db",
                        name=node.name,
                        old_version=db_node.version,
                        new_version=node.version
                    )
                    db_node.label = node.label
                    db_node.node_type = raw_node_type
                    db_node.description = node.description
                    db_node.version = node.version
                    db_node.category = category_id
                    db_node.group = node.group
                    db_node.icon = node.icon or "bot"
                    db_node.color = node.color or "#5E0CEC"
                    db_node.badge = node.badge
                    db_node.sub_label = node.sub_label
                    db_node.user_properties = user_props_code
                    db_node.system_properties = system_props_code
                    db_node.input_contract = node.input_contract if node.input_contract is not None else {}
                    db_node.output_contract = node.output_contract if node.output_contract is not None else {}
                    db_node.customer_id = db_cust_id
                    session.add(db_node)
                else:
                    cls.logger.info(
                        "skipping_db_overwrite_version_not_newer",
                        name=node.name,
                        db_version=db_node.version,
                        node_version=node.version
                    )

                # Automatically assign/enable node for customer-scoped custom nodes
                if cust_id is not None and cust_id != 0:
                    stmt_cn = select(CustomerNodeDB).where(
                        CustomerNodeDB.customer_id == cust_id,
                        CustomerNodeDB.node_name == node.name
                    )
                    res_cn = await session.execute(stmt_cn)
                    db_cn = res_cn.scalar_one_or_none()
                    if not db_cn:
                        new_cn = CustomerNodeDB(
                            customer_id=cust_id,
                            node_name=node.name,
                            properties={},
                            is_enabled=True
                        )
                        session.add(new_cn)

    @classmethod
    async def _load_plugins_from_directory(cls, directory_path: str, customer_id: int):
        """
        Loads custom nodes (plugins) from subdirectories of `directory_path`.
        If customer_id is 0, these are system plugins.
        """
        from importlib.machinery import SourceFileLoader
        import sys

        cls.logger.info("loading_plugins_from_directory_started", path=directory_path, tenant_id=customer_id)
        
        abs_path = os.path.abspath(directory_path)
        if not os.path.exists(abs_path):
            cls.logger.debug("plugin_storage_path_not_found", tenant_id=customer_id, path=abs_path)
            return

        cls.logger.info("scanning_plugins", tenant_id=customer_id, path=abs_path)
        
        # Scan sub-directories in storage_path
        for item in os.listdir(abs_path):
            subdir_path = os.path.join(abs_path, item)
            if not os.path.isdir(subdir_path):
                continue
            
            # Skip python internal directories
            if item.startswith("__"):
                continue

            manifest_path = os.path.join(subdir_path, "manifest.json")
            if not os.path.exists(manifest_path):
                cls.logger.debug("manifest_missing, ignoring the plugin", path=subdir_path)
                continue

            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
            except Exception as e:
                cls.logger.error("failed_to_parse_manifest", path=manifest_path, error=str(e))
                continue

            # Check mandatory fields
            mandatory_fields = ["name", "label", "file_name", "class_name"]
            missing = [field for field in mandatory_fields if not manifest.get(field)]
            if missing:
                cls.logger.warning(
                    "custom_plugin_rejected_missing_fields",
                    path=manifest_path,
                    missing_fields=missing
                )
                continue

            script_path = os.path.join(subdir_path, manifest["file_name"])
            if not os.path.exists(script_path):
                cls.logger.error("plugin_script_missing", path=script_path)
                continue

            # Add subdir to sys.path to allow imports from within plugin code
            if subdir_path not in sys.path:
                sys.path.append(subdir_path)

            try:
                if customer_id != 0:
                    module_name = f"client_{customer_id}_{item}"
                    node_name = f"client_{customer_id}_{manifest['name']}"
                else:
                    module_name = f"system_plugin_{item}"
                    node_name = manifest["name"]

                # Register LazyPluginNode to defer loading code/packages until first execution
                lazy_instance = LazyPluginNode(
                    plugin_dir=subdir_path,
                    script_path=script_path,
                    class_name=manifest["class_name"],
                    module_name=module_name,
                    name=node_name,
                    label=manifest.get("label", manifest["name"]),
                    description=manifest.get("description", ""),
                    version=manifest.get("version", "1.0.0"),
                    category=manifest.get("category", "Custom"),
                    group=manifest.get("group", "Custom"),
                    icon=manifest.get("icon", "bot"),
                    color=manifest.get("color", "#5E0CEC"),
                    badge=manifest.get("badge", "Plugin"),
                    sub_label=manifest.get("sub_label"),
                    node_type=(manifest.get("node_type") or "NODE").upper(),
                    user_properties=manifest.get("user_properties", []),
                    system_properties=manifest.get("system_properties", []),
                    input_contract=manifest.get("input_contract", {}),
                    output_contract=manifest.get("output_contract", {}),
                    customer_id=customer_id
                )

                # Sync node manifest with DB first, then register & initialize in memory
                await cls.add_node_to_db(lazy_instance)
                await cls.register(lazy_instance)
                cls.logger.info(
                    "plugin_registered_lazy",
                    customer_id=customer_id,
                    node_name=lazy_instance.name
                )
            except Exception as e:
                cls.logger.error(
                    "failed_to_register_plugin",
                    customer_id=customer_id,
                    path=subdir_path,
                    error=str(e)
                )

    @classmethod
    async def _load_customer_custom_plugins(cls):
        """
        Queries CustomerDB for tenants with custom plugins enabled and loads their custom nodes.
        """
        from app.core.database import AsyncSessionLocal
        from app.models.db_models import CustomerDB
        from sqlalchemy import select

        cls.logger.info("loading_customer_custom_plugins_started")
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(CustomerDB).where(
                    CustomerDB.custom_plugins_enabled == True,
                    CustomerDB.plugin_storage_path != None
                )
                result = await session.execute(stmt)
                customers = result.scalars().all()

                for customer in customers:
                    storage_path = customer.plugin_storage_path
                    if not storage_path:
                        continue
                    # Resolve to absolute path if relative
                    abs_path = os.path.abspath(storage_path)
                    await cls._load_plugins_from_directory(abs_path, customer.id)
        except Exception as e:
            cls.logger.error("error_loading_customer_custom_plugins", error=str(e))