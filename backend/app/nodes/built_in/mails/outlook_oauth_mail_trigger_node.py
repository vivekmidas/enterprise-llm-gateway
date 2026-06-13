
from typing import Dict, Any, List, Optional
import asyncio
from app.nodes.base import TriggerNode
from app.nodes.built_in.mails.abstract_mail_node import EmailTriggerNode
import httpx


class OutlookEmailTriggerNode(EmailTriggerNode):
    """
    Outlook-specific OAuth polling trigger.
    """
    name: str = "outlook_email_trigger"
    label: str = "Outlook OAuth Trigger"
    description: str = "Polls Outlook via Microsoft Graph API for new messages."

    property_schema: List[Dict[str, Any]] = [
        {
            "key": "credentialId",
            "label": "Outlook Account",
            "type": "credential",
            "credentialType": "outlook_oauth2",
            "description": "Connect your Microsoft Outlook account."
        },
        {"key": "folder", "label": "Mail Folder", "type": "string", "default": "Inbox"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
        {"key": "mark_as_read", "label": "Mark as Read", "type": "boolean", "default": True},
    ]

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Registers the workflow and creates a Microsoft Graph Subscription.
        """
        # 1. Base registration (via TriggerNode)
        await super().activate(agent_node_id, workflow_config)

        # 2. Resolve instance configuration
        config = self._get_node_config(agent_node_id, workflow_config)

        # 3. Create Subscription
        try:
            access_token = await self._authenticate(agent_node_id, config)
            async with httpx.AsyncClient() as client:
                sub_payload = {
                    "changeType": "created",
                    "notificationUrl": self._get_webhook_url(agent_node_id),
                    "resource": "me/messages",
                    "expirationDateTime": "2025-12-31T11:00:00.0000000Z", # Should be calculated (max 4230 mins)
                    "clientState": "secretClientState"
                }
                resp = await client.post("https://graph.microsoft.com/v1.0/subscriptions", 
                                        headers={"Authorization": f"Bearer {access_token}"}, json=sub_payload)
                resp.raise_for_status()
            self.logger.info("outlook_subscription_created", agent_node_id=agent_node_id)
        except Exception as e:
            self.logger.error("outlook_subscription_failed", error=str(e), agent_node_id=agent_node_id)

        if agent_node_id in self._polling_tasks:
            self._polling_tasks[agent_node_id].cancel()

    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]) -> Optional[str]:
        """Implements Outlook/Microsoft Graph OAuth flow."""
        credential_id = config.get("credentialId")
        if not credential_id:
            raise ValueError("No Outlook credential selected.")

        credential = await self._get_credential(credential_id)
        if not credential:
            raise ValueError(f"Credential with ID {credential_id} not found.")

        auth_data = credential.auth_data or {}
        return auth_data.get("access_token")

    async def _handle_api_notification(self, agent_node_id: str, payload: Dict[str, Any]):
        """
        Processes incoming Microsoft Graph resource notifications.
        """
        workflow_config = self._workflows.get(agent_node_id, {})
        config = self._get_node_config(agent_node_id, workflow_config)
        try:
            access_token = await self._authenticate(agent_node_id, config)
            async with httpx.AsyncClient() as client:
                for notification in payload.get("value", []):
                    resource = notification.get("resource") # e.g. "Users/.../Messages/..."
                    if not resource: continue
                    
                    # Fetch the actual message
                    msg_resp = await client.get(f"https://graph.microsoft.com/v1.0/{resource}", 
                                              headers={"Authorization": f"Bearer {access_token}"})
                    msg_resp.raise_for_status()
                    msg = msg_resp.json()
                    payload = self._format_msg({
                        "from": msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown"),
                        "subject": msg.get("subject", "No Subject"),
                        "body": msg.get("body", {}).get("content", ""),
                        "id": msg.get("id")
                    })
                    
                    await self.execute_dynamic_agent(agent_node_id, payload)
                    
                    # 3. Mark as read
                    if config.get("mark_as_read", True):
                        await client.patch(f"https://graph.microsoft.com/v1.0/me/messages/{msg['id']}", 
                                         headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                                         json={"isRead": True})

        except Exception as e:
            self.logger.error("outlook_webhook_processing_failed", error=str(e), agent_node_id=agent_node_id)