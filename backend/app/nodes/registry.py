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
                    if "property_schema" in external_data:
                        node.property_schema = external_data["property_schema"]
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
    async def auto_discover(cls):
        """
        Dynamically discovers nodes in built-in and plugin directories.
        """
        cls.logger.info("auto_discover_started")
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
            "auto_discover_completed", 
            nodes_count=len(cls._nodes), 
            registered_nodes=list(cls._nodes.keys())
        )

    @classmethod
    async def sync_with_db(cls):
        """
        Syncs discovered nodes and categories from files/classes into the database.
        This ensures the DB is populated for the API to consume.
        """
        from app.core.database import AsyncSessionLocal
        from app.models.db_models import NodeDB, CategoryDB
        from sqlalchemy import select
        client_id = 0  # Placeholder for SaaS multi-tenancy support
        cls.logger.info("syncing_registry_with_db")
        
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # 1. Sync Categories from data/node_categories.json
                base_dir = Path(__file__).resolve().parent.parent.parent
                cat_file = base_dir / "data" / "node_categories.json"
                if cat_file.exists():
                    try:
                        with open(cat_file, "r") as f:
                            cats = json.load(f)
                            for cat in cats:
                                stmt = select(CategoryDB).where(CategoryDB.name == cat["name"])
                                result = await session.execute(stmt)
                                db_cat = result.scalar_one_or_none()
                                if not db_cat:
                                    session.add(CategoryDB(name=cat["name"], icon=cat.get("icon"), color=cat.get("color")))
                                    cls.logger.info("category_created_in_db", name=cat["name"])
                                # We skip updating categories to preserve UI edits
                    except Exception as e:
                        cls.logger.error("failed_to_sync_categories", error=str(e))

                # 2. Sync Discovered Nodes
                for node_name, node in cls._nodes.items():
                    # Prepared for SaaS: client_id filtering would happen here
                    stmt = select(NodeDB).where(NodeDB.name == node_name)
                    result = await session.execute(stmt)
                    db_node = result.scalar_one_or_none()
                    
                    if not db_node:
                        # Only add if it doesn't exist to prevent overwriting UI customizations
                        session.add(NodeDB(
                            name=node.name,
                            label=node.label,
                            description=node.description,
                            version=node.version,
                            category=node.category,
                            icon=node.icon,
                            color=node.color,
                            badge=node.badge,
                            sub_label=node.sub_label,
                            property_schema=node.property_schema,
                            properties=node.properties
                        ))
                        cls.logger.info("node_added_to_catalog", name=node_name, client_id=client_id)
                    else:
                        # If it exists, pull properties from DB into the in-memory registry
                        if db_node.properties:
                            node.properties.update(db_node.properties)
                        cls.logger.debug("node_properties_synced_from_db", name=node_name, client_id=client_id)

            cls.logger.info("nodes_synced_with_db", count=len(cls._nodes), client_id=client_id)

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
                if issubclass(obj, BaseNode) and obj is not BaseNode:
                    cls.logger.info("found_node_class", class_name=obj.__name__, module=module_name)
                    try:
                        instance = obj()
                        await cls.register(instance)
                    except Exception as e:
                        cls.logger.error("node_instantiation_failed", node=obj.__name__, error=str(e))
        except Exception as e:
            cls.logger.error("node_module_load_failed", module=module_name, error=str(e))