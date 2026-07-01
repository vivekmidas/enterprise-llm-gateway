# backend/app/nodes/built_in/webhook/api_webhook_agent.py

import abc
import asyncio
import json
import time
from typing import Any, ClassVar, Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import PrivateAttr
from uvicorn.config import Config

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import TriggerNode
from app.nodes.built_in.webhook.base.base_webhook_agent import WebhookAgent


class DBWebhookAgent(WebhookAgent, abc.ABC):

    name: str = "db_webhook_agent"
    description: str = "DB Webhook Agent for DB operations"
    version: str = "1.0.0"
    category: str = 10
    node_type: str = "trigger"
    #label="Base DB webhook agent",
    #group="Databases",
    #icon="database",
    #color="#ff00aaa",
    #badge="badge",
    #sub_label="sub_label",
    
    async def validate_request(self, request: Request, payload: str) -> bool:
        # Custom authorization logic
        expected_key = self.properties.get("api_key")
        if not expected_key:
            
            return True
            
        provided_key = request.headers.get("X-Stock-Token")
        return provided_key == expected_key



    async def execute(self, inp: NodeInput) -> NodeOutput:
        self.logger.info("DB webhook_execution_started", trace_id=inp.trace_id, agent_name=self.name)
        self.logger.debug("DB webhook_execution_data", data=inp.data,properties=self.properties)
        
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success",
            metadata={"source": self.name},
        )
    
