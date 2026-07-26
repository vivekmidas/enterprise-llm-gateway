import jwt
import structlog
from datetime import datetime, timedelta
from typing import Optional
from app.core.config import get_settings
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import uuid
import structlog
from app.core.observability import get_logger
logger = get_logger()
import json
from fastapi import Request, HTTPException,status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

settings = get_settings()
#logger = structlog.get_logger(__name__)

PUBLIC_PATHS:json = {
        "/auth/login",
        "/auth/refresh",
        "/auth/register",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/health",
        "/metrics"
        }
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": data.get("user_id"),                    # User ID
        "role" : data.get("role"),
        "tenant": data.get("customer_id"),
        "domain":data.get("domain"),
        "status":data.get("status"),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),          # Unique token ID for revocation
        "type": "access",
        "iss": settings.ISSUER,
        "aud": settings.AUDIENCE,
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
        options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["exp", "sub", "iat", "jti"]
            },
            audience=settings.AUDIENCE,
            issuer=settings.ISSUER
        )
        return decoded
    except jwt.PyJWTError:
        return None

def create_refresh_token(subject: str) -> str:
    """
    Create long-lived refresh token
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "sub": subject,
        "domain":data.get("domain"),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

class AuthenticationMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        # Pre-processing: Log or modify the request
        if request.method == "OPTIONS":
            return await call_next(request)

        logger.debug("Request details", client_host=request.client.host, client_port=request.client.port, request_url=request.url, method=request.method,x_forwarded_for=request.headers.get("x-forwarded-for"))

        # Skip public endpoints
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)
        
        auth = request.headers.get("Authorization")

        if not auth or not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing token"}
            )

        try:
            token = auth.split()[1]
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                audience=settings.AUDIENCE,
                issuer=settings.ISSUER
            )
            if (request.url.path.startswith("/admin")):
                if (payload.get("role") not in ["admin","system_admin"]):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Not authorized to access admin panel"}
                    )
            request.state.user = {
                "id": payload["sub"],
                "domain":payload.get("domain"),
                "status":payload.get("status"),
                "role": payload.get("role"),
                "sid": payload.get("sid"),
                "tenant": payload.get("tenant")
            }

        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"}
            )
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", str(e))
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid token"}
            )
        except Exception as e:  # Catch unexpected errors
            logger.error("Token validation error", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed"}
            )
        except jwt.PyJWTError as e:
            logger.error("invalid_token", error=str(e))
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )

        return await call_next(request)
