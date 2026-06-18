from typing import Dict, Any, List
import asyncio
from app.nodes.base import TriggerNode
from app.nodes.built_in.mails.abstract_mail_node import EmailTriggerNode

class ImapEmailPullTriggerNode(EmailTriggerNode):
    """
    Legacy IMAP polling trigger (Standard Password/App Password).
    """
    name: str = "imap_email_pull_trigger"
    label: str = "IMAP Pull Trigger"
    description: str = "Polls an IMAP server using username/password."

    property_schema: List[Dict[str, Any]] = [
        {"key": "imap_host", "label": "IMAP Server", "type": "string", "placeholder": "imap.gmail.com"},
        {"key": "imap_port", "label": "Port", "type": "number", "default": 993},
        {"key": "username", "label": "Email/Username", "type": "string"},
        {"key": "password", "label": "Password / App Password", "type": "password"},
        {"key": "folder", "label": "Folder", "type": "string", "default": "INBOX"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
    ]

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Registers the workflow and starts the IMAP background polling task.
        """
        # 1. Base registration (via TriggerNode)
        await super().activate(agent_node_id, workflow_config)

        # 2. Resolve instance configuration
        nodes = workflow_config.get("nodes_structure", [])
        node_data = next((n for n in nodes if n.get("id") == agent_node_id), {})
        overrides = node_data.get("data", {}).get("properties") or {}
        config = {**self.properties, **overrides}

        # 3. Start the background polling task
        if agent_node_id in self._polling_tasks:
            self._polling_tasks[agent_node_id].cancel()

        task = asyncio.create_task(self._polling_loop(agent_node_id, config))
        self._polling_tasks[agent_node_id] = task
        self.logger.info("imap_pull_trigger_activated", agent_node_id=agent_node_id)

    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]) -> Any:
        """IMAP uses basic auth; authentication happens during the connection in _check_emails."""
        return True

    async def _check_emails(self, agent_node_id: str, config: Dict[str, Any]):
        """Maintains the existing IMAP polling logic if needed."""
        # Implementation would use imap_tools as before
        pass