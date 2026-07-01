from typing import Dict, Any, List, Optional
import asyncio
import datetime
import abc
from app.nodes.base import TriggerNode
from pydantic import PrivateAttr, Field
from app.nodes.properties import safe_int
from app.core.database import AsyncSessionLocal
from app.models.db_models import CredentialDB
from sqlalchemy import select

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
        """Loads global node properties from the central store via BaseNode."""
        await super().init()

    async def _get_credential(self, credential_id: Any) -> Optional[CredentialDB]:
        """Fetches a credential from the central store."""
        if not credential_id:
            return None
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CredentialDB).where(CredentialDB.id == int(credential_id)))
            return result.scalar_one_or_none()

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

    @abc.abstractmethod
    async def _handle_api_notification(self, agent_node_id: str, payload: Dict[str, Any]):
        """Handles incoming webhook notifications from the provider."""
        pass

    def _get_webhook_url(self, agent_node_id: str) -> str:
        """Constructs the public webhook URL for this node instance."""
        base_url = "https://your-gateway-domain.com" # Should come from config/env
        return f"{base_url}/api/webhooks/email/{agent_node_id}"

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
        interval = max(safe_int(config.get("check_interval"), 60), 10)
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
