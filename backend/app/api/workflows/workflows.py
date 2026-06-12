import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from app.workflows.store import update_node_tokens_in_db

router = APIRouter()
logger = structlog.get_logger(__name__)

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