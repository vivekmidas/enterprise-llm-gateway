# backend/app/nodes/built_in/webhook/stock_api_agent.py

from typing import Dict, Any, List
from fastapi import Request
from app.nodes.built_in.webhook.base.base_webhook_agent import BaseWebhookAgent

class QdrantWebhookNode(BaseWebhookAgent):
    name: str = "qdrant_webhook_node"
    label: str = "Qdrant Webhook Node"
    description: str = "Triggers workflows on Qdrant Vector Database events"
    category: str = "VectorDb"
    icon: str = "database"
    color: str = "#2ECC71"
    
    system_properties: Dict[str, Any] = {
        "base_path": "qdrant-webhook"
    }
    user_properties: Dict[str, Any] = {}
    
    async def init(self):
        await super().init()
        
    async def validate_request(self, request: Request, payload: str) -> bool:
        # Custom authorization logic
        expected_key = self.properties.get("api_key")
        if not expected_key:
            return True
            
        provided_key = request.headers.get("X-Qdrant-Token") 
        return provided_key == expected_key
