from typing import Dict, Any, Optional
from fastapi import Request
from app.nodes.built_in.webhook.base.base_webhook_agent import BaseWebhookAgent

class WebhookAgent(BaseWebhookAgent):
    """
    Standard Webhook Agent.
    Validates optional Bearer tokens configured by admins.
    """

    # Define default contracts and properties

    async def validate_request(self, request: Request, payload: str) -> bool:
        # Check standard headers for Authorization bearer token if configured
        expected_token = self.properties.get("auth_token")
        if not expected_token:
            return True

        provided_token = request.headers.get("Authorization")
        if not provided_token:
            return False

        if provided_token.startswith("Bearer "):
            provided_token = provided_token[7:]

        return provided_token == expected_token