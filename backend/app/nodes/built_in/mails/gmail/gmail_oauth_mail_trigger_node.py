"""Backward-compatibility shim for GmailEmailTriggerNode."""
from app.nodes.built_in.mails.gmail.gmail_oauth_mail_trigger_node import GmailEmailTriggerNode

__all__ = ["GmailEmailTriggerNode"]

