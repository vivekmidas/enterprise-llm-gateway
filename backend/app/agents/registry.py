import importlib
import pkgutil
from typing import Dict
from app.agents.base import BaseAgent

class AgentRegistry:
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent_instance: BaseAgent):
        cls._agents[agent_instance.name] = agent_instance
        print(f"✅ Agent registered: {agent_instance.name} v{agent_instance.version}")

    @classmethod
    def get_agent(cls, name: str):
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls):
        return list(cls._agents.keys())

    @classmethod
    def auto_discover(cls):
        """Auto-register all agents in built_in and custom folders"""
        package = "app.agents"
        for module_info in pkgutil.iter_modules([f"backend/app/agents"]):
            if module_info.name in ["built_in", "custom"]:
                try:
                    module = importlib.import_module(f"{package}.{module_info.name}")
                    # Import all .py files inside
                    for sub_info in pkgutil.iter_modules(module.__path__):
                        if not sub_info.name.startswith("__"):
                            importlib.import_module(f"{package}.{module_info.name}.{sub_info.name}")
                except Exception as e:
                    print(f"Warning: Could not load {module_info.name}: {e}")
