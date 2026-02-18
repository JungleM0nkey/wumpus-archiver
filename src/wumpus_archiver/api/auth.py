"""API authentication middleware."""

import hmac
import logging

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


_security_dependency = Security(security)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = _security_dependency,
) -> None:
    """Require valid Bearer token for state-modifying endpoints.

    If no API_SECRET is configured, all requests are allowed (development mode).
    """
    api_secret = getattr(request.app.state, "api_secret", None)
    if api_secret is None:
        return

    if credentials is None or not hmac.compare_digest(credentials.credentials, api_secret):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
