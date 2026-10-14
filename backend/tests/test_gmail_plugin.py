import pytest
from app.nodes.registry import NodesRegistry
from app.nodes.built_in.mails.gmail.gmail_client import GmailClient
from backend.app.nodes.built_in.mails.gmail.gmail_client import GmailClient as ShimGmailClient
from app.nodes.built_in.mails.gmail.gmail_oauth_mail_trigger_node import GmailEmailTriggerNode
from backend.app.nodes.built_in.mails.gmail.gmail_oauth_mail_trigger_node import GmailEmailTriggerNode as ShimGmailEmailTriggerNode

@pytest.mark.asyncio
async def test_gmail_node_auto_discovery():
    await NodesRegistry.node_auto_discover()
    node = NodesRegistry.get_node("gmail_email_trigger")
    assert node is not None
    assert node.name == "gmail_email_trigger"
    assert isinstance(node, GmailEmailTriggerNode)

def test_gmail_client_import_and_shim():
    assert GmailClient is ShimGmailClient
    assert GmailEmailTriggerNode is ShimGmailEmailTriggerNode

def test_gmail_client_message_parsing():
    client = GmailClient(
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
        access_token="test-access-token"
    )
    
    mock_msg = {
        "id": "18a12345678",
        "threadId": "18a12345678",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Tue, 13 Oct 2026 12:00:00 +0000"}
            ],
            "body": {
                # Base64 url-encoded "Hello, world!"
                "data": "SGVsbG8sIHdvcmxkIQ=="
            }
        }
    }
    
    parsed = client.parse_message(mock_msg)
    assert parsed["id"] == "18a12345678"
    assert parsed["subject"] == "Test Subject"
    assert parsed["from"] == "sender@example.com"
    assert parsed["to"] == "recipient@example.com"
    assert parsed["body"] == "Hello, world!"

