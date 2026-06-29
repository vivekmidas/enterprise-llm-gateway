# backend/nodes/built-in/api_request_node.py
from app.nodes.built_in.api_request_node import ApiRequestNode
from typing import Dict, Any, List, Optional
import time
import urllib.parse
import ast
import json
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.http_client import HttpClient, ApiResponse
from pydantic import BaseModel, Field

class StocksApiRequestNode(ApiRequestNode):
    """Generic External API Request Node - Flexible & Production Ready"""
    name: str = "stocks_api_request_node"
    node_type: str = "NODE"
    label: str = "Stocks API Request NODE"
    description: str = "Call STOCKS API to get latest stock quotes"
    category: str = "stocks"
    icon: str = "📈"

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        self.logger.debug("Validating input", trace_id=inp.trace_id,node_name=self.name,name=__name__)
        await super().validate_input(inp)
        if not inp.data:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message="Input rules not matched"
            )
        return None



