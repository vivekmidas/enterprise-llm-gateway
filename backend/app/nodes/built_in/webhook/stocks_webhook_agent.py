# backend/app/nodes/built_in/webhook/stock_api_agent.py

from typing import Dict, Any, List
from fastapi import Request
from app.nodes.built_in.webhook.base_webhook_agent import BaseWebhookAgent

class StocksWebhookAgent(BaseWebhookAgent):
    name: str = "stocks_webhook_agent"
    label: str = "Stocks Webhook Agent"
    description: str = "Triggers workflows on stock price movements or API alerts"
    category: str = "Integration"
    icon: str = "trending-up"
    color: str = "#2ECC71"
    
 
    
    async def validate_request(self, request: Request, payload: str) -> bool:
        # Custom authorization logic
        expected_key = self.properties.get("api_key")
        if not expected_key:
            return True
            
        provided_key = request.headers.get("X-Stock-Token")
        return provided_key == expected_key
