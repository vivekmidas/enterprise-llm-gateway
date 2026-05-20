import importlib
import pkgutil
from typing import Dict
from app.agents.base import BaseAgent

class AgentRegistry:
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent):
        cls._agents[agent.name] = agent
        print(f"✅ Agent registered: {agent.name} v{agent.version}")

    @classmethod
    def get_agent(cls, name: str):
        return cls._agents.get(name)

    @classmethod
    def list_agents(cls):
        return list(cls._agents.keys())

    @classmethod
    def auto_discover(cls):
        """Auto discover and register all agents on startup"""
        base_path = "app.agents"
        
        # Discover built_in agents
        for module_info in pkgutil.iter_modules(["backend/app/agents/built_in"]):
            if module_info.name.startswith("__"):
                continue
            try:
                importlib.import_module(f"{base_path}.built_in.{module_info.name}")
            except Exception as e:
                print(f"Warning loading {module_info.name}: {e}")