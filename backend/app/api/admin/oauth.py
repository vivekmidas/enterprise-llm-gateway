import httpx
from fastapi import APIRouter, Request, HTTPException, Query, Body
from fastapi.responses import RedirectResponse
import structlog
from typing import Optional, List, Dict, Any
from app.core.database import AsyncSessionLocal
from app.models.db_models import CredentialDB, OAuthProviderDB
from sqlalchemy import select

router = APIRouter(prefix="/admin/oauth", tags=["Authentication"])
logger = structlog.get_logger(__name__)

@router.get("/providers", response_model=List[Dict[str, Any]])
async def list_providers():
    """Lists all configured OAuth providers."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(OAuthProviderDB))
        providers = result.scalars().all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "label": p.label,   
                "description": p.description,
                "icon": p.icon,
                "callback_url": p.callback_url,
                "auth_url": p.auth_url,
                "token_url": p.token_url,
                "default_scopes": p.default_scopes
            } for p in providers
        ]

@router.post("/providers")
async def create_provider(data: Dict[str, Any] = Body(...)):
    """Creates a new OAuth provider configuration."""
    async with AsyncSessionLocal() as session:
        provider = OAuthProviderDB(**data)
        session.add(provider)
        await session.commit()
        return {"status": "success", "id": provider.id}

@router.get("/connect/{provider}")
async def connect_provider(
    provider: str, 
    client_id: str, 
    client_secret: str,
    name: str = "New Connection"
):
    async with AsyncSessionLocal() as session:
        stmt = select(OAuthProviderDB).where(OAuthProviderDB.name == provider)
        result = await session.execute(stmt)
        provider_config = result.scalar_one_or_none()

    if provider_config:
        # Encapsulate identity in state (Simplified for this example)
        state = f"{client_id}|{client_secret}|{name}"
        
        # Build URL dynamically from DB config
        auth_url = (
            f"{provider_config.auth_url}?response_type=code"
            f"&client_id={client_id}&redirect_uri={provider_config.callback_url}"
            f"&scope={provider_config.default_scopes}&access_type=offline&prompt=consent&state={state}"
        )
        return RedirectResponse(auth_url)
    
    raise HTTPException(status_code=400, detail="Unsupported provider")

@router.get("/callback/{provider}")
async def auth_callback(provider: str, code: str, state: str):
    """
    Handles the OAuth callback, exchanges code for tokens, and stores them.
    """
    logger.info("auth_callback_received", provider=provider)

    client_id, client_secret, name = state.split("|")

    async with AsyncSessionLocal() as session:
        stmt = select(OAuthProviderDB).where(OAuthProviderDB.name == provider)
        result = await session.execute(stmt)
        provider_config = result.scalar_one_or_none()

    if provider_config:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(provider_config.token_url, data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": provider_config.callback_url,
                    "grant_type": "authorization_code",
                })
                resp.raise_for_status() # Raise an exception for bad status codes
                token_data = resp.json()

                # Save to centralized 'credentials' table
                async with AsyncSessionLocal() as session:
                    credential = CredentialDB(
                        name=name,
                        type="gmail_oauth2",
                        config={"client_id": client_id, "client_secret": client_secret},
                        auth_data=token_data
                    )
                    session.add(credential)
                    await session.commit()
                    await session.refresh(credential)

                # Return a script that closes the window and sends a message to the opener
                # This allows the frontend to update its state with the new credential ID
                return RedirectResponse(
                    url=f"/admin/oauth/callback/success?credentialId={credential.id}&credentialName={name}",
                    status_code=302
                )
            except httpx.HTTPStatusError as e:
                logger.error("gmail_token_exchange_failed", error=str(e), response=e.response.text)
                raise HTTPException(status_code=e.response.status_code, detail=f"Failed to exchange token: {e.response.text}")
            except Exception as e:
                logger.error("gmail_auth_callback_error", error=str(e))
                raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

    raise HTTPException(status_code=400, detail="Unsupported provider")

@router.get("/callback/success")
async def auth_callback_success(credentialId: int, credentialName: str, origin: str = "*"):
    """
    Renders a success page that closes the popup and sends data to the opener.
    """
    return f"""
    <html>
        <head><title>Authentication Success</title></head>
        <body style="font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; flex-direction: column; color: #374151;">
            <p>Authentication successful! You can close this window.</p>
            <script>
                window.opener.postMessage({{ type: 'CREDENTIAL_CREATED', credentialId: '{credentialId}', credentialName: '{credentialName}' }}, '{origin}');
                window.close();
            </script>
        </body>
    </html>
    """

@router.get("/credentials", response_model=List[Dict[str, Any]])
async def list_credentials(type: Optional[str] = None):
    """Lists available credentials, optionally filtered by type."""
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        query = select(CredentialDB)
        if type:
            query = query.where(CredentialDB.type == type)
        result = await session.execute(query)
        credentials = result.scalars().all()
        return [{"id": str(cred.id), "name": cred.name, "type": cred.type} for cred in credentials]
    
