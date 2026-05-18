import importlib
import pkgutil
from .base import BaseAgent
from typing import Dict

class AgentRegistry:
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent):
        cls._agents[agent.name] = agent
        print(f"✅ Agent registered: {agent.name} v{agent.version}")

    @classmethod
    def get_agent(cls, name: str) -> BaseAgent | None:
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls):
        return list(cls._agents.keys())

    @classmethod
    def auto_discover(cls):
        """Auto discover and register agents in built_in and custom"""
        for module_info in pkgutil.iter_modules(__path__):
            if module_info.name.startswith('built_in') or module_info.name.startswith('custom'):
                try:
                    module = importlib.import_module(f".{module_info.name}", package=__package__)
                except:
                    continue