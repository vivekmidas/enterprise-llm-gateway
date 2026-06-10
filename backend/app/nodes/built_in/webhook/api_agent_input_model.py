# basic model structure for agent input exeends NodeInput and can be extended with additional fields as needed
from pydantic import BaseModel
from app.nodes.base import NodeInput, NodeOutput

class WebhookAgentInput(NodeInput):
    # Example field for incoming webhook data, can be extended with more fields as needed
    payload: dict
    