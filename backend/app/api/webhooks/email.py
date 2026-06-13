import json
import base64
import structlog
from typing import Dict, Any
from pydantic import BaseModel, Field
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, status, Path
from  app.workflows.store import update_node_tokens_in_db
from app.nodes.registry import NodesRegistry
from app.nodes.built_in.mails.pull_mail_trigger_node import ImapEmailPullTriggerNode # Assuming this is the correct path

router = APIRouter(prefix="/webhooks/email", tags=["Email Webhooks"])
logger = structlog.get_logger(__name__)

@router.post("/{agent_node_id}")
async def receive_email_webhook(agent_node_id: str = Path(..., description="The ID of the agent node"), request: Request = None):
    """
    Receives email notifications from providers (e.g., Gmail Pub/Sub, Microsoft Graph).
    Dispatches the notification to the appropriate ImapEmailTriggerNode instance.
    """
    logger.info("email_webhook_received", agent_node_id=agent_node_id, headers=request.headers)

    # Get the generic email trigger node instance from the registry
    # Assuming 'email_trigger' is the name of the node (as updated in the diff above)
    node_instance = NodesRegistry.get_node("email_trigger") 
    if not node_instance or not isinstance(node_instance, ImapEmailPullTriggerNode):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Email trigger node 'email_trigger' not found or not configured correctly.")

    # Ensure the specific agent_node_id is active and configured for API
    workflow_config = node_instance._workflows.get(agent_node_id)
    if not workflow_config:
        logger.warning("webhook_for_inactive_workflow", agent_node_id=agent_node_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow for agent_node_id '{agent_node_id}' not active.")

    node_data = next((n for n in workflow_config.get("nodes_structure", []) if n["id"] == agent_node_id), None)
    if not node_data:
        logger.warning("webhook_for_missing_node_data", agent_node_id=agent_node_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node data for agent_node_id '{agent_node_id}' not found in workflow config.")

    config = {**node_instance.properties, **node_data.get("data", {}).get("properties", {})}
    auth_method = config.get("auth_method")

    if auth_method not in ["Gmail OAuth2", "Outlook OAuth2"]:
        logger.warning("webhook_for_non_api_auth_method", agent_node_id=agent_node_id, auth_method=auth_method)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Auth method '{auth_method}' does not support webhooks.")

    try:
        # Read the raw body to handle different webhook formats
        raw_body = await request.body()
        notification_payload = json.loads(raw_body.decode('utf-8'))
        
        # Microsoft Graph validation: respond to validation tokens
        if auth_method == "Outlook OAuth2" and "validationToken" in request.query_params:
            validation_token = request.query_params["validationToken"]
            logger.info("outlook_webhook_validation_request", agent_node_id=agent_node_id)
            return validation_token # Respond with the token to validate the webhook

        await node_instance._handle_api_notification(agent_node_id, notification_payload)
        return {"status": "success", "message": "Notification processed."}
    except json.JSONDecodeError:
        logger.error("webhook_invalid_json_payload", agent_node_id=agent_node_id, raw_body=raw_body.decode('utf-8', errors='ignore'))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")
    except Exception as e:
        logger.error("email_webhook_processing_failed", agent_node_id=agent_node_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process webhook: {e}")

class RefreshTokenRequest(BaseModel):
    """
    Request body for updating access and refresh tokens for a workflow node.
    """
    workflow_id: str = Field(..., description="The ID of the workflow.")
    node_id: str = Field(..., description="The ID of the specific node within the workflow.")
    access_token: str = Field(..., description="The new access token to store.")
    refresh_token: Optional[str] = Field(None, description="The new refresh token to store (optional).")

@router.put("/refresh-token", summary="Update access and refresh tokens for a workflow node")
async def refresh_node_tokens(request: RefreshTokenRequest):
    """
    Updates the `access_token` and `refresh_token` properties for a specific node
    within a workflow. This is typically used for OAuth flows where tokens
    need to be refreshed periodically.
    """
    logger.info("refresh_token_request_received", workflow_id=request.workflow_id, node_id=request.node_id)
    try:
        await update_node_tokens_in_db(
            workflow_id=request.workflow_id,
            node_id=request.node_id,
            access_token=request.access_token,
            refresh_token=request.refresh_token
        )
        logger.info("tokens_updated_successfully", workflow_id=request.workflow_id, node_id=request.node_id)
        return {"message": "Tokens updated successfully."}
    except HTTPException as e:
        logger.error("failed_to_update_tokens_http_exception", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e.detail))
        raise e
    except Exception as e:
        logger.error("failed_to_update_tokens_internal_error", workflow_id=request.workflow_id, node_id=request.node_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update tokens: {str(e)}"
        )