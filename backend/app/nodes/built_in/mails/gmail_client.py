import base64
from typing import Dict, Any, List, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


class GmailClient:
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly"
    ]

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: Optional[str] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = access_token

        self._creds = None
        self._service = None

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    def authenticate(self):
        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES,
        )

        if not creds.valid:
            creds.refresh(Request())

        self.access_token = creds.token
        self._creds = creds

        return creds

    # -------------------------------------------------------------------------
    # Gmail Service
    # -------------------------------------------------------------------------

    def service(self):
        if self._service:
            return self._service

        creds = self.authenticate()

        self._service = build(
            "gmail",
            "v1",
            credentials=creds,
            cache_discovery=False,
        )

        return self._service

    def watch(self, topic_name: str, label_ids: List[str] = None) -> Dict[str, Any]:
        """
        Starts watching the mailbox. 
        Notifications are sent to the provided Google Cloud Pub/Sub topic.
        """
        service = self.service()
        body = {
            'topicName': topic_name,
            'labelIds': label_ids or ['INBOX']
        }
        return (
            service.users()
            .watch(userId='me', body=body)
            .execute()
        )

    # -------------------------------------------------------------------------
    # Profile
    # -------------------------------------------------------------------------

    def get_profile(self) -> Dict[str, Any]:
        service = self.service()

        return (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

    # -------------------------------------------------------------------------
    # List Messages
    # -------------------------------------------------------------------------

    def list_messages(
        self,
        query: str = "is:unread",
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:

        service = self.service()

        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results,
            )
            .execute()
        )

        return result.get("messages", [])

    # -------------------------------------------------------------------------
    # Get Message
    # -------------------------------------------------------------------------

    def get_message(
        self,
        message_id: str,
    ) -> Dict[str, Any]:

        service = self.service()

        return (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

    # -------------------------------------------------------------------------
    # Mark Read
    # -------------------------------------------------------------------------

    def mark_as_read(
        self,
        message_id: str,
    ):

        service = self.service()

        return (
            service.users()
            .messages()
            .modify(
                userId="me",
                id=message_id,
                body={
                    "removeLabelIds": [
                        "UNREAD"
                    ]
                },
            )
            .execute()
        )

    # -------------------------------------------------------------------------
    # Body Extraction
    # -------------------------------------------------------------------------

    def extract_text(
        self,
        payload: Dict[str, Any],
    ) -> str:

        if (
            payload.get("mimeType") == "text/plain"
            and payload.get("body", {}).get("data")
        ):
            return base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode(
                "utf-8",
                errors="ignore",
            )

        for part in payload.get("parts", []):
            text = self.extract_text(part)

            if text:
                return text

        return ""

    # -------------------------------------------------------------------------
    # Convert Gmail Message -> Event
    # -------------------------------------------------------------------------

    def parse_message(
        self,
        message: Dict[str, Any],
    ) -> Dict[str, Any]:

        payload = message.get(
            "payload",
            {}
        )

        headers = {
            h["name"].lower(): h["value"]
            for h in payload.get(
                "headers",
                []
            )
        }

        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "subject": headers.get(
                "subject",
                "",
            ),
            "from": headers.get(
                "from",
                "",
            ),
            "to": headers.get(
                "to",
                "",
            ),
            "date": headers.get(
                "date",
                "",
            ),
            "body": self.extract_text(
                payload
            ),
        }

    # -------------------------------------------------------------------------
    # Poll Unread Emails
    # -------------------------------------------------------------------------

    def get_unread_events(
        self,
        folder: str = "INBOX",
        mark_as_read: bool = True,
    ) -> List[Dict[str, Any]]:

        query = "is:unread"

        if folder != "INBOX":
            query += f" label:{folder}"

        messages = self.list_messages(
            query=query,
            max_results=100,
        )

        events = []

        for msg_meta in messages:

            msg = self.get_message(
                msg_meta["id"]
            )

            event = self.parse_message(
                msg
            )

            events.append(event)

            if mark_as_read:
                self.mark_as_read(
                    msg_meta["id"]
                )

        return events