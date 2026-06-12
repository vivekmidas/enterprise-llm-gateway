from typing import Dict, Any, List, Optional
import asyncio
import datetime
import abc
from app.nodes.base import TriggerNode
from pydantic import PrivateAttr, Field

class EmailTriggerNode(TriggerNode, abc.ABC):
    """
    Abstract Base Class for Email Pull/Polling Triggers.
    Handles the common background polling loop and lifecycle management.
    """
    category: str = "Communication"
    version: str = "1.0.0"
    icon: str = "mail"
    color: str = "#EA4335"

    # Shared state for all email pull nodes
    _polling_tasks: Dict[str, asyncio.Task] = PrivateAttr(default_factory=dict)
    _oauth_tokens: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    async def init(self) -> None:
        await super().init()

    def _get_node_config(self, agent_node_id: str, workflow_config: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts and merges instance-specific properties from the workflow config."""
        node_data = next(
            (n for n in workflow_config.get("nodes_structure", []) if n["id"] == agent_node_id), 
            None
        )
        props = node_data.get("data", {}).get("properties", {}) if node_data else {}
        return {**self.properties, **props}

    @abc.abstractmethod
    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Abstract method to register the workflow and handle node-specific startup.
        Subclasses MUST call super().activate() to ensure workflow registration in TriggerNode.
        """
        await super().activate(agent_node_id, workflow_config)

    @abc.abstractmethod
    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]) -> Any:
        """Standardized method to resolve/refresh credentials for the provider."""
        pass

    async def deactivate(self, agent_node_id: str):
        """Stops the polling loop and cleans up."""
        if agent_node_id in self._polling_tasks:
            task = self._polling_tasks.pop(agent_node_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if agent_node_id in self._workflows:
            del self._workflows[agent_node_id]
            
        self.logger.info("email_trigger_deactivated", agent_node_id=agent_node_id)

    async def _polling_loop(self, agent_node_id: str, config: Dict[str, Any]):
        """Generic loop that executes the specific _check_emails logic."""
        interval = max(int(config.get("check_interval", 60)), 10)
        while True:
            try:
                await self._check_emails(agent_node_id, config)
            except Exception as e:
                self.logger.error("email_poll_failed", error=str(e), agent_node_id=agent_node_id)
            
            await asyncio.sleep(interval)

    async def _check_emails(self, agent_node_id: str, config: Dict[str, Any]):
        """To be implemented by specific provider classes."""
        pass

    def _format_msg(self, msg_data: Dict[str, Any]) -> Dict[str, Any]:
        """Standardizes the payload for downstream nodes."""
        return {
            "from": msg_data.get("from"),
            "to": msg_data.get("to"),
            "subject": msg_data.get("subject"),
            "datetime": datetime.datetime.utcnow().isoformat(),
            "content": msg_data.get("body"),
            "uid": msg_data.get("id")
        }
