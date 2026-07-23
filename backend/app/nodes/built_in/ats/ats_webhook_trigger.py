"""
NOT A NEW NODE.

Use existing node: api_webhook_agent
Configure system_properties.base_path = "ats" in the workflow JSON.

The /webhooks/run/{base_path} gateway (app/api/webhooks/run.py) will route
POST /webhooks/run/ats → the workflow containing this trigger node.

This file is kept for documentation only and is NOT imported by the registry.
"""
