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

# ==============================================================================
# BLOCK COMMENT: PUBLIC ENDPOINTS & TOKEN EXTRACTION (BEARER + HTTPONLY COOKIE)
# ==============================================================================
PUBLIC_PATHS:json = {
        "/auth/login",
        "/auth/logout",
        "/auth/refresh",
        "/auth/register",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/health",
        "/metrics"
        }
# BLOCK COMMENT: JWT CLAIMS ENRICHMENT (DOMAIN, CUSTOMER_ID, DOMAIN_ID, USER_ID, ROLE, PERMISSIONS)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Primary domain ID calculation (e.g., 'legal', 'education')
    allowed_domains = data.get("allowed_domains", [])
    domain_id = data.get("domain_id") or (allowed_domains[0] if allowed_domains else "legal")

    to_encode = {
        "sub": str(data.get("user_id") or data.get("sub")),    # User ID
        "user_id": str(data.get("user_id") or data.get("sub")),
        "email": data.get("email"),
        "role": data.get("role"),
        "role_type": data.get("role_type"),
        "customer_id": data.get("customer_id"),
        "tenant": data.get("customer_id"),                     # Alias for backwards compatibility
        "domain": data.get("domain"),                          # Tenant company domain (e.g. azbpartners.com)
        "domain_id": domain_id,                                # Active vertical domain (legal, education)
        "allowed_domains": allowed_domains,                    # List of assigned vertical domains
        "status": data.get("status"),
        "permissions": data.get("permissions", []),
        "default_route": data.get("default_route"),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),                              # Unique token ID for revocation
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

def cors_json_response(request: Request, status_code: int, content: dict) -> JSONResponse:
    origin = request.headers.get("origin")
    headers = {
        "Access-Control-Allow-Credentials": "true",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return JSONResponse(status_code=status_code, content=content, headers=headers)


class AuthenticationMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        # Pre-processing: Handle CORS pre-flight
        if request.method == "OPTIONS":
            return await call_next(request)

        logger.debug("Request details", client_host=request.client.host, client_port=request.client.port, request_url=request.url, method=request.method,x_forwarded_for=request.headers.get("x-forwarded-for"))

        # Skip public endpoints
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)
        
        # ==============================================================================
        # BLOCK COMMENT: EXTRACT TOKEN FROM AUTHORIZATION HEADER OR HTTPONLY COOKIE
        # ==============================================================================
        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth.split()[1]
        elif request.cookies.get("token"):
            token = request.cookies.get("token")

        if not token:
            return cors_json_response(
                request=request,
                status_code=401,
                content={"detail": "Missing token"}
            )

        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                audience=settings.AUDIENCE,
                issuer=settings.ISSUER
            )
            if request.url.path.startswith("/admin"):
                user_role = (payload.get("role") or "").lower()
                user_perms = payload.get("permissions", [])
                is_admin_user = (
                    user_role in ["admin", "system_admin", "tenant_admin"]
                    or "*:*:*" in user_perms
                    or "admin:*:*" in user_perms
                    or any(p.startswith("admin:") for p in user_perms)
                )
                if not is_admin_user:
                    return cors_json_response(
                        request=request,
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Not authorized to access admin panel"}
                    )
            request.state.user = {
                "id": payload["sub"],
                "domain":payload.get("domain"),
                "status":payload.get("status"),
                "role": payload.get("role"),
                "sid": payload.get("sid"),
                "tenant": payload.get("tenant"),
                "permissions": payload.get("permissions", [])
            }

        except jwt.ExpiredSignatureError:
            return cors_json_response(
                request=request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"}
            )
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", str(e))
            return cors_json_response(
                request=request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid token"}
            )
        except jwt.PyJWTError as e:
            logger.error("invalid_token", error=str(e))
            return cors_json_response(
                request=request,
                status_code=401,
                content={"detail": "Invalid token"}
            )
        except Exception as e:  # Catch unexpected errors
            logger.error("Token validation error", exc_info=True)
            return cors_json_response(
                request=request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed"}
            )

        return await call_next(request)
