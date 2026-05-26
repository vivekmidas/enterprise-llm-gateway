import importlib
import inspect
import os
import pkgutil
import structlog
from typing import Dict, List, Optional, Type
from app.agents.built_in.base import BaseAgent

logger = structlog.get_logger(__name__)

class AgentRegistry:
    """
    Registry for managing and dynamically discovering agents.
    """
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent):
        """Registers an instantiated agent."""
        if not agent.name or agent.name == "base_agent":
            return
        cls._agents[agent.name] = agent
        logger.info("agent_registered", name=agent.name, category=agent.category, version=agent.version)

    @classmethod
    def get_agent(cls, name: str) -> Optional[BaseAgent]:
        """Retrieves an agent by its unique name."""
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls) -> List[BaseAgent]:
        """Returns a list of all registered agents."""
        return list(cls._agents.values())

    @classmethod
    def auto_discover(cls):
        """
        Dynamically discovers agents in built-in and plugin directories.
        """
        # 1. Discover built-in agents
        try:
            import app.agents.built_in as built_in_pkg
            if hasattr(built_in_pkg, "__file__") and built_in_pkg.__file__:
                package_path = os.path.dirname(built_in_pkg.__file__)
                cls._scan_package(package_path, "app.agents.built_in")
            elif hasattr(built_in_pkg, "__path__"):
                for path in built_in_pkg.__path__:
                    cls._scan_package(path, "app.agents.built_in")
        except ImportError:
            logger.warning("built_in_agents_package_not_found")

        # 2. Discover plugin agents from 'plugins/agents' folder (allows dropping new .py files)
        plugins_dir = os.path.join(os.getcwd(), "plugins", "agents")
        if os.path.exists(plugins_dir):
            import sys
            if plugins_dir not in sys.path:
                sys.path.append(plugins_dir)
            cls._scan_directory(plugins_dir)

    @classmethod
    def _scan_package(cls, package_path: str, prefix: str):
        """Walks through a package and its sub-packages to find agents."""
        for _, module_name, _ in pkgutil.walk_packages([package_path], prefix=f"{prefix}."):
            cls._load_module(module_name)

    @classmethod
    def _scan_directory(cls, directory: str):
        """Scans a flat directory for python files containing agents."""
        for filename in os.listdir(directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                cls._load_module(module_name)

    @classmethod
    def _load_module(cls, module_name: str):
        """Loads a module and registers any BaseAgent subclasses found within."""
        try:
            module = importlib.import_module(module_name)
            # Reload to ensure we pick up the latest code if dropped at runtime
            importlib.reload(module)
            
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseAgent) and obj is not BaseAgent:
                    try:
                        instance = obj()
                        cls.register(instance)
                    except Exception as e:
                        logger.error("agent_instantiation_failed", agent=obj.__name__, error=str(e))
        except Exception as e:
            logger.error("agent_module_load_failed", module=module_name, error=str(e))