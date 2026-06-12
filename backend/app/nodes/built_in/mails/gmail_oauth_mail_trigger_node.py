from typing import Dict, Any, List, Optional
import asyncio
import base64
from app.nodes.base import NodeInput, NodeOutput
from pydantic import PrivateAttr, Field
from app.nodes.built_in.mails.abstract_mail_node import EmailTriggerNode

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


class GmailEmailTriggerNode(EmailTriggerNode):
    """
    Gmail-specific OAuth polling trigger.
    """
    name: str = "gmail_email_trigger"
    label: str = "Gmail OAuth Trigger"
    description: str = "Polls Gmail via OAuth2 API for new messages."
    # _WEB_GMAIL={"web":{"client_id":"766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com",
    #                    "project_id":"agent-gateway-499207","auth_uri":"https://accounts.google.com/o/oauth2/auth",
    #                    "token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs",
    #                    "client_secret":"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"}}

    property_schema: List[Dict[str, Any]] = [
        {"key": "client_id", "label": "Client ID", "type": "string"},
        {"key": "client_secret", "label": "Client Secret", "type": "password"},
        {"key": "refresh_token", "label": "Refresh Token", "type": "password"},
        {"key": "folder", "label": "Label/Folder", "type": "string", "default": "INBOX"},
        {"key": "check_interval", "label": "Poll Interval (sec)", "type": "number", "default": 60},
        {"key": "mark_as_read", "label": "Mark as Read", "type": "boolean", "default": True},
    ]
    
    async def init(self) -> None:
        await super().init()
        self.logger.info("gmail_trigger_initialized")

    async def _authenticate(self, agent_node_id: str, config: Dict[str, Any]):
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        token_info = self._oauth_tokens.get(agent_node_id, {})

        creds = Credentials(
            token="ya29.a0AT3oNZ9skJgkJf89KB9cP3_mR9mOWVsyxS0wHkDy68fkN9mpiaHk-r2xJBK4E9eFEPHWRzK2hG6RXALp8AnWiIWbtrgsv4ZkemDu072pkeF364xiPlLuQBEkJfoRuue2WG3I-k6ef_QdWMz3LwfpOJXMIdVauzMcWEJSGMY7_Ofqh44BCHf60E6Pc1rDaStmL5JW-ooaCgYKAQYSARYSFQHGX2MiRBI_-6J4l7Bt6xuNqLf8nQ0206",
            refresh_token="1//0g8BSjwqicUENCgYIARAAGBASNwF-L9IrmJY_jb2o1lr2_ryZY8qoV7fmWXTFHFgbQa6qAKweAGNjfbP-Lc-J1qKui7cy3C1v3tE",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="766633200484-v42quiqo5o3evg81ulrcud4np356o7be.apps.googleusercontent.com",
            #config.get("client_id") or self._WEB_GMAIL["web"]["client_id"],
            client_secret="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",
            # account=config.get("client_secret") or self._WEB_GMAIL["web"]["client_secret"],
            scopes=scopes,
        )

        if creds and not creds.valid:
            try:
                await asyncio.to_thread(creds.refresh, Request())
            except Exception as e:
                self.logger.error("gmail_token_refresh_failed", error=str(e), agent_node_id=agent_node_id)
                raise e
            self._oauth_tokens[agent_node_id] = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token
            }

        return creds

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Registers the workflow and starts the Gmail background polling task.
        Explicitly handles Gmail OAuth setup during activation.
        """
        # 1. Base registration (via TriggerNode)
        await super().activate(agent_node_id, workflow_config)
       

        # 2. Resolve instance configuration
        config = self._get_node_config(agent_node_id, workflow_config)

        # 3. Perform initial Gmail-specific authentication/token refresh
        try:
            await self._authenticate(agent_node_id, config)
            self.logger.info("gmail_auth_check_successful", agent_node_id=agent_node_id)
        except Exception as e:
            self.logger.error("gmail_initial_authentication_failed", error=str(e), agent_node_id=agent_node_id)
            # We continue activation so the loop can retry later, or you might choose to return here

        # 4. Start the background polling task (Cancel existing if re-activating)
        if agent_node_id in self._polling_tasks:
            self._polling_tasks[agent_node_id].cancel()

        #task = asyncio.create_task(self._polling_loop(agent_node_id, config))
        #self._polling_tasks[agent_node_id] = task
        self.logger.info("gmail_trigger_activated", agent_node_id=agent_node_id)

    async def _check_emails(self, agent_node_id: str, config: Dict[str, Any]):
        """
        Gmail-specific OAuth polling implementation.
        """
        try:
            creds = await self._authenticate(agent_node_id, config)
            if not creds:
                return

            # 1. Build Service (Blocking call, offload to thread)
            service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=creds, cache_discovery=False)
            folder = config.get("folder", "INBOX")
            query = "is:unread"
            if folder != "INBOX":
                query += f" label:{folder}"

            self.logger.debug("gmail_polling_messages", agent_node_id=agent_node_id, query=query)
            results = await asyncio.to_thread(service.users().messages().list(userId='me', q=query).execute)
            messages = results.get('messages', [])

            for msg_meta in messages:
                # 3. Fetch full message content (Blocking call)
                msg = await asyncio.to_thread(service.users().messages().get(userId='me', id=msg_meta['id'], format='full').execute)
                payload = msg.get('payload', {})
                headers = payload.get('headers', [])
                
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown")
                
                # Extract text body recursively
                body = ""
                parts_to_process = [payload]
                while parts_to_process:
                    current_part = parts_to_process.pop()
                    if current_part.get('mimeType') == 'text/plain' and current_part.get('body', {}).get('data'):
                        body = base64.urlsafe_b64decode(current_part['body']['data']).decode('utf-8')
                        break
                    if 'parts' in current_part:
                        parts_to_process.extend(current_part['parts'])

                # 3. Trigger Dynamic Agent
                event_data = self._format_msg({
                    "from": sender,
                    "subject": subject,
                    "body": body,
                    "id": msg_meta['id']
                })
                
                self.logger.info("gmail_new_email_trigger", msg_id=msg_meta['id'], subject=subject)
                await self.execute_dynamic_agent(agent_node_id, event_data)

                # 4. Mark as read
                if config.get("mark_as_read", True):
                    await asyncio.to_thread(service.users().messages().batchModify(
                        userId='me',
                        body={'ids': [msg_meta['id']], 'removeLabelIds': ['UNREAD']}
                    ).execute)

        except Exception as e:
            self.logger.error("gmail_poll_failed", error=str(e), agent_node_id=agent_node_id)
