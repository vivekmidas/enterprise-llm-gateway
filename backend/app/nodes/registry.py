import importlib
import inspect
import os
import pkgutil
import structlog
from typing import Dict, List, Optional, Type
from app.nodes.built_in.base import BaseNode

logger = structlog.get_logger(__name__)

class NodesRegistry: 
    """
    Registry for managing and dynamically discovering nodes.
    """
    _nodes: Dict[str, BaseNode] = {}

    @classmethod
    def register(cls, agent: BaseNode):
        """Registers an instantiated node."""
        if not agent.name or agent.name == "base_node":
            logger.debug("skip_registration_base_agent", agent_name=agent.name)
            return
        cls._nodes[agent.name] = agent
        logger.info("node_registered", name=agent.name, category=agent.category, version=agent.version)

    @classmethod
    def get_node(cls, name: str) -> Optional[BaseNode]:
        """Retrieves a node by its unique name."""
        logger.debug("get_node_request", name=name)
        node = cls._nodes.get(name)
        if node:
            logger.debug("get_node_hit", name=name)
        else:
            logger.debug("get_node_miss", name=name)
        return node

    @classmethod
    def list_nodes(cls) -> List[BaseNode]:
        """Returns a list of all registered nodes."""
        
        logger.debug("list_nodes_request", count=len(cls._nodes))
        return list(cls._nodes.values())

    @classmethod
    def auto_discover(cls):
        """
        Dynamically discovers nodes in built-in and plugin directories.
        """
        logger.info("auto_discover_started")
        # 1. Discover built-in nodes
        try:
            import app.nodes.built_in as built_in_pkg
            if hasattr(built_in_pkg, "__file__") and built_in_pkg.__file__:
                package_path = os.path.dirname(built_in_pkg.__file__)
                logger.info("scanning_builtin_package_path", path=package_path)
                cls._scan_package(package_path, "app.nodes.built_in")
            elif hasattr(built_in_pkg, "__path__"):
                for path in built_in_pkg.__path__:
                    logger.info("scanning_builtin_package_path", path=path)
                    cls._scan_package(path, "app.nodes.built_in")
        except ImportError:
            logger.warning("built_in_agents_package_not_found")

        # 2. Discover plugin agents from 'plugins/agents' folder (allows dropping new .py files)
        plugins_dir = os.path.join(os.getcwd(), "plugins", "agents")
        if os.path.exists(plugins_dir):
            import sys
            if plugins_dir not in sys.path:
                sys.path.append(plugins_dir)
            logger.info("scanning_plugins_directory", path=plugins_dir)
            cls._scan_package(plugins_dir, "")
        else:
            logger.debug("plugins_directory_not_found", path=plugins_dir)

    @classmethod
    def _scan_package(cls, package_path: str, prefix: str):
        """Walks through a package and its sub-packages to find agents."""
        logger.info("scanning_package", package_path=package_path, prefix=prefix)

        # 1. Load the root package itself first (to find agents in __init__.py)
        if prefix:
            cls._load_module(prefix)

        # 2. Recursively find and load all sub-modules
        for _, module_name, ispkg in pkgutil.walk_packages([package_path], prefix=f"{prefix}." if prefix else ""):
            if ispkg:
                logger.info("scanning_directory", module=module_name)
            cls._load_module(module_name)

    @classmethod
    def _scan_directory(cls, directory: str):
        """Scans a flat directory for python files containing agents."""
        logger.debug("scanning_directory", directory=directory)
        for filename in os.listdir(directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                cls._load_module(module_name)

    @classmethod
    def _load_module(cls, module_name: str):
        """Loads a module and registers any BaseAgent subclasses found within."""
        logger.debug("loading_module", module=module_name)
        try:
            # Import the module. 
            # We avoid importlib.reload() as it can break class identity checks (issubclass)
            # by creating fresh class objects that differ from the ones in the registry's memory.
            module = importlib.import_module(module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseNode) and obj is not BaseNode:
                    logger.info("found_node_class", class_name=obj.__name__, module=module_name)
                    try:
                        instance = obj()
                        cls.register(instance)
                    except Exception as e:
                        logger.error("node_instantiation_failed", node=obj.__name__, error=str(e))
        except Exception as e:
            logger.error("node_module_load_failed", module=module_name, error=str(e))