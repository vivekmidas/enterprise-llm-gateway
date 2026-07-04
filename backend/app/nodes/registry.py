import importlib
import inspect
import json
import os
import pkgutil
from pathlib import Path
import structlog
from typing import Dict, List, Optional, Type
from app.nodes.base import BaseNode

class NodesRegistry: 
    """
    Registry for managing and dynamically discovering nodes.
    """
    _nodes: Dict[str, BaseNode] = {}
    logger = structlog.get_logger("NodesRegistry")

    @classmethod
    async def register(cls, agent: BaseNode):
        """Registers an instantiated node."""
        if not agent.name or agent.name == "base_node":
            cls.logger.debug("skip_registration_base_agent", agent_name=agent.name)
            return

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
                   
                    if "input_contract" in external_data:
                        node.input_contract = external_data["input_contract"]
                    if "output_contract" in external_data:
                        node.output_contract = external_data["output_contract"]
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

        # 2. Discover plugin agents from 'plugins/agents' folder (allows dropping new .py files)
        plugins_dir = os.path.join(os.getcwd(), "plugins", "nodes")
        if os.path.exists(plugins_dir):
            import sys
            if plugins_dir not in sys.path:
                sys.path.append(plugins_dir)
            cls.logger.info("scanning_plugins_directory", path=plugins_dir)
            await cls._scan_package([plugins_dir], "")
        else:
            cls.logger.debug("plugins_directory_not_found", path=plugins_dir)

        # Log the "output" of the discovery process
        cls.logger.info(
            "node_auto_discover_completed", 
            nodes_count=len(cls._nodes), 
            registered_nodes=list(cls._nodes.keys())
        )

        # Sync definitions with DB to load global properties/schema overrides 
        await cls.sync_with_db()

    @classmethod
    async def sync_with_db(cls):
        """
        Syncs discovered nodes and categories from files/classes into the database.
        This ensures the DB is populated for the API to consume.
        """
        from app.core.database import AsyncSessionLocal
        from app.models.db_models import NodeDB, CategoryDB
        from sqlalchemy import select

        cls.logger.info("syncing_registry_with_db")

        def merge_properties(db_props, code_props):
            # If both are dicts, merge them directly, preserving DB values
            if isinstance(db_props, dict) and isinstance(code_props, dict):
                merged = dict(code_props)
                merged.update(db_props)
                return merged

            # Otherwise, treat as lists of property entries (schemas)
            db_list = db_props if isinstance(db_props, list) else []
            if isinstance(db_props, dict):
                db_list = [{"key": k, "value": v} for k, v in db_props.items()]

            code_list = code_props if isinstance(code_props, list) else []
            if isinstance(code_props, dict):
                code_list = [{"key": k, "default": v} for k, v in code_props.items()]

            # Decode stringified items if they exist
            parsed_db_list = []
            for item in db_list:
                if isinstance(item, str):
                    try:
                        parsed_db_list.append(json.loads(item))
                    except Exception:
                        pass
                elif isinstance(item, dict):
                    parsed_db_list.append(item)

            parsed_code_list = []
            for item in code_list:
                if isinstance(item, str):
                    try:
                        parsed_code_list.append(json.loads(item))
                    except Exception:
                        pass
                elif isinstance(item, dict):
                    parsed_code_list.append(item)

            db_keys = {item.get("key"): item for item in parsed_db_list if isinstance(item, dict) and "key" in item}
            code_keys = {item.get("key"): item for item in parsed_code_list if isinstance(item, dict) and "key" in item}

            merged_list = []

            # 1. Keep existing DB entries, merging structural metadata from code
            for key, db_item in db_keys.items():
                if key in code_keys:
                    updated_item = {**code_keys[key], **db_item}
                    if "value" in db_item:
                        updated_item["value"] = db_item["value"]
                    elif "default" in db_item:
                        updated_item["default"] = db_item["default"]
                    merged_list.append(updated_item)
                else:
                    # Retain properties deprecated in code but configured in DB for safety
                    merged_list.append(db_item)

            # 2. Add new properties defined in code
            for key, code_item in code_keys.items():
                if key not in db_keys:
                    merged_list.append(code_item)

            return merged_list

        async with AsyncSessionLocal() as session:
            async with session.begin():
                # 2. Sync Discovered Nodes
                for node_name, node in cls._nodes.items():
                    stmt = select(NodeDB).where(NodeDB.name == node_name)
                    result = await session.execute(stmt)
                    db_node = result.scalars().first()

                    # Load original, unmutated defaults from Python node class definition
                    user_props_code = []
                    system_props_code = []

                    def get_clean_default(field_obj):
                        if not field_obj:
                            return []
                        val = getattr(field_obj, "default", [])
                        if val is None or "Undefined" in val.__class__.__name__:
                            factory = getattr(field_obj, "default_factory", None)
                            if factory is not None:
                                try:
                                    val = factory()
                                except Exception:
                                    val = []
                            else:
                                val = []
                        return val

                    if hasattr(node.__class__, "model_fields"):
                        user_props_code = get_clean_default(node.__class__.model_fields.get("user_properties"))
                        system_props_code = get_clean_default(node.__class__.model_fields.get("system_properties"))
                    elif hasattr(node.__class__, "__fields__"):
                        user_props_code = get_clean_default(node.__class__.__fields__.get("user_properties"))
                        system_props_code = get_clean_default(node.__class__.__fields__.get("system_properties"))
                    else:
                        user_props_code = node.user_properties or []
                        system_props_code = node.system_properties or []

                    if not db_node:
                        cls.logger.info("registering_new_node_to_db", name=node_name)
                        
                        # Dynamically map node category string to database category ID
                        node_category = str(getattr(node, "category", "") or "Custom")
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

                        new_db_node = NodeDB(
                            name=node.name,
                            label=node.label,
                            node_type=node.node_type.upper() if node.node_type else "NODE",
                            description=node.description,
                            version=node.version,
                            category=category_id,
                            group=node.group,
                            icon="bot",
                            color=node.color,
                            badge=node.badge,
                            sub_label=node.sub_label,
                            user_properties=user_props_code,
                            system_properties=system_props_code,
                            input_contract=node.input_contract,
                            output_contract=node.output_contract
                        )
                        session.add(new_db_node)
                    # else:
                    #     cls.logger.info("syncing_existing_node_schema_to_db", name=node_name)

                    #     # Merge properties non-destructively
                    #     merged_user_props = merge_properties(db_node.user_properties, user_props_code)
                    #     merged_sys_props = merge_properties(db_node.system_properties, system_props_code)

                    #     # Update core implementations fields, keeping user-customized ones
                    #     db_node.node_type = node.node_type.upper() if node.node_type else db_node.node_type
                    #     db_node.version = node.version or db_node.version
                    #     db_node.input_contract = node.input_contract or db_node.input_contract
                    #     db_node.output_contract = node.output_contract or db_node.output_contract
                    #     db_node.user_properties = merged_user_props
                    #     db_node.system_properties = merged_sys_props

                    #     session.add(db_node)

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
        """Loads a module and registers any BaseAgent subclasses found within."""
        cls.logger.debug("loading_module", module=module_name)
        try:
            # Import the module. 
            # We avoid importlib.reload() as it can break class identity checks (issubclass)
            # by creating fresh class objects that differ from the ones in the registry's memory.
            module = importlib.import_module(module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseNode) and obj is not BaseNode and not inspect.isabstract(obj):
                    cls.logger.info("found_node_class", class_name=obj.__name__, module=module_name)
                    try:
                        instance = obj()
                        await cls.register(instance)
                    except Exception as e:
                        cls.logger.error("node_instantiation_failed", node=obj.__name__, error=str(e))
        except Exception as e:
            cls.logger.error("node_module_load_failed", module=module_name, error=str(e))