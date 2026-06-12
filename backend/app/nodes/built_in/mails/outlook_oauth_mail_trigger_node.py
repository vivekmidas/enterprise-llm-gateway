
from typing import Dict, Any, List, Optional
import asyncio
from app.nodes.base import TriggerNode
from app.nodes.built_in.mails.abstract_mail_node import EmailTriggerNode


class OutlookEmailTriggerNode(EmailTriggerNode):
    """
    Outlook-specific OAuth polling trigger.
    """
    name: str = "outlook_email_trigger"
    label: str = "Outlook OAuth Trigger"
    description: str = "Polls Outlook via Microsoft Graph API for new messages."

    property_schema: List[Dict[str, Any]] = [
        {"key": "client_id", "label": "Application (client) ID", "type": "string"},
        {"key": "client_secret", "label": "Client Secret", "type": "password"},
        {"key": "tenant_id", "label": "Directory (tenant) ID", "type": "string", "default": "common"},
        {"key": "refresh_token", "label": "Refresh Token", "type": "password"},
        {"key": "folder", "label": "Mail Folder", "type": "string", "default": "Inbox"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
        {"key": "mark_as_read", "label": "Mark as Read", "type": "boolean", "default": True},
    ]

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Registers the workflow and starts the Outlook background polling task.
        Explicitly handles Outlook OAuth setup during activation.
        """
        # 1. Base registration (via TriggerNode)
        await super().activate(agent_node_id, workflow_config)

        # 2. Resolve instance configuration
        config = self._get_node_config(agent_node_id, workflow_config)

        # 3. Perform initial Outlook-specific authentication/token refresh
        try:
            await self._authenticate(agent_node_id, config)
        except Exception as e:
            self.logger.error("outlook_initial_authentication_failed", error=str(e), agent_node_id=agent_node_id)

        # 4. Start the background polling task
        if agent_node_id in self._polling_tasks:
            self._polling_tasks[agent_node_id].cancel()

        #task = asyncio.create_task(self._polling_loop(agent_node_id, config))
        #self._polling_tasks[agent_node_id] = task
        self.logger.info("outlook_trigger_activated", agent_node_id=agent_node_id)

    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]) -> Optional[str]:
        """Implements Outlook/Microsoft Graph OAuth flow."""
        import httpx
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        refresh_token = config.get("refresh_token")
        tenant_id = config.get("tenant_id", "common")

        async with httpx.AsyncClient() as client:
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            resp = await client.post(token_url, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/Mail.ReadWrite offline_access"
            })
            resp.raise_for_status()
            token_data = resp.json()
            
            # Update DB if refresh token changed
            if "refresh_token" in token_data and token_data["refresh_token"] != refresh_token:
                from app.workflows.store import update_workflow_node_properties
                workflow_id = self._workflows.get(agent_node_id, {}).get("id")
                if workflow_id:
                    await update_workflow_node_properties(
                        workflow_id, agent_node_id, {"refresh_token": token_data["refresh_token"]}
                    )
            return token_data["access_token"]

    async def _check_emails(self, agent_node_id: str, config: Dict[str, Any]):
        """
        Outlook-specific OAuth polling logic using Microsoft Graph.
        """
        import httpx
        try:
            access_token = await self._authenticate(agent_node_id, config)
            
            async with httpx.AsyncClient() as client:
                folder = config.get("folder", "Inbox")
                graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
                msg_resp = await client.get(graph_url, headers={"Authorization": f"Bearer {access_token}"}, params={
                    "$filter": "isRead eq false",
                    "$select": "subject,from,body,id"
                })
                msg_resp.raise_for_status()
                
                for msg in msg_resp.json().get("value", []):
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
            self.logger.error("outlook_poll_failed", error=str(e), agent_node_id=agent_node_id)