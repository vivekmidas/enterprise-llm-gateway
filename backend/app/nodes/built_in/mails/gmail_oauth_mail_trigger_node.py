from typing import Dict, Any, List, Optional
import asyncio
import base64
from app.nodes.base import NodeInput, NodeOutput
from pydantic import PrivateAttr, Field
from app.nodes.built_in.mails.gmail_client import GmailClient
from app.nodes.built_in.mails.abstract_mail_node import EmailTriggerNode

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import json



class GmailEmailTriggerNode(EmailTriggerNode):
    """
    Gmail-specific OAuth polling trigger.
    """
    name: str = "gmail_email_trigger"
    label: str = "Gmail OAuth Trigger"
    description: str = "Polls Gmail via OAuth2 API for new messages."

    property_schema: List[Dict[str, Any]] = [
        {
            "key": "credentialId",
            "label": "Gmail Account",
            "type": "credential",
            "credentialType": "gmail_oauth2",
            "description": "Select an existing connection or create a new one."
        },
        {"key": "folder", "label": "Label/Folder", "type": "string", "default": "INBOX"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
        {"key": "mark_as_read", "label": "Mark as Read", "type": "boolean", "default": True},
    ]
    
    async def init(self) -> None:
        await super().init()
        self.logger.info("gmail_trigger_initialized")

    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]) -> GmailClient:
        client = GmailClient(
            client_id=config.get('auth_client_id'),
            client_secret=config.get('auth_client_secret'),
            refresh_token=config.get('refresh_token'),
            access_token=config.get('access_token')
        )
        await asyncio.to_thread(client.authenticate)
        return client

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Registers the workflow and sets up Gmail Watch (Push Notifications).
        """
        # 1. Base registration (via TriggerNode)
        await super().activate(agent_node_id, workflow_config)
       
        # 2. Resolve instance configuration
        nodes = workflow_config.get("nodes_structure", [])
        node_data = next((n for n in nodes if n.get("id") == agent_node_id), {})
        overrides = node_data.get("data", {}).get("properties") or {}
        config = {**self.properties, **overrides}

        # 3. Setup Gmail Watch (requires a pre-configured GCP Pub/Sub Topic)
        try:
            client = await self._authenticate(agent_node_id, config)
            # Note: topic_name must be configured in your Google Cloud Console
            topic_name = config.get("topic_name", "projects/agent-gateway-499207/topics/agent-gateway")
            await asyncio.to_thread(client.watch, topic_name=topic_name)
            self.logger.info("gmail_watch_established", agent_node_id=agent_node_id)
        except Exception as e:
            self.logger.error("gmail_watch_setup_failed", error=str(e), agent_node_id=agent_node_id)

        # 4. No polling loop started here as we are using Push
        if agent_node_id in self._polling_tasks:
            self._polling_tasks[agent_node_id].cancel()

    async def _handle_api_notification(self, agent_node_id: str, payload: Dict[str, Any]):
        """
        Processes the Google Pub/Sub push notification.
        """
        workflow_config = self._workflows.get(agent_node_id, {})
        config = self._get_node_config(agent_node_id, workflow_config)
        try:
            # Google Pub/Sub data is base64 encoded
            data_str = base64.b64decode(payload['message']['data']).decode('utf-8')
            data = json.loads(data_str)
            history_id = data.get('historyId')

            client = await self._authenticate(agent_node_id, config)
            service = await asyncio.to_thread(client.service)

            # Fetch the changes since the last historyId
            history = await asyncio.to_thread(service.users().history().list(userId='me', startHistoryId=history_id).execute)
            
            for record in history.get('history', []):
                messages_added = record.get('messagesAdded', [])
                for msg_item in messages_added:
                    msg_id = msg_item['message']['id']
                    msg = await asyncio.to_thread(client.get_message, msg_id)
                    event_data = client.parse_message(msg)
                    
                    self.logger.info("gmail_push_trigger", msg_id=msg_id)
                    await self.execute_dynamic_agent(agent_node_id, self._format_msg(event_data))

                    if config.get("mark_as_read", True):
                        await asyncio.to_thread(client.mark_as_read, msg_id)

        except Exception as e:
            self.logger.error("gmail_webhook_processing_failed", error=str(e), agent_node_id=agent_node_id)
