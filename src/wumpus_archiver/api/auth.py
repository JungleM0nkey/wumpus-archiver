"""Bearer-token authentication for state-changing API endpoints."""

import secrets

from fastapi import HTTPException, Request, status

from wumpus_archiver.api.deps import ApiAuthToken

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def _extract_bearer_token(header: str | None) -> str | None:
    """Extract the credentials from an ``Authorization: Bearer <token>`` header.

    Args:
        header: Raw ``Authorization`` header value, if any.

    Returns:
        The bearer token, or None if the header is missing or malformed.
    """
    if not header:
        return None
    scheme, _, credentials = header.partition(" ")
    credentials = credentials.strip()
    if scheme.lower() != "bearer" or not credentials:
        return None
    return credentials


async def require_api_token(api_auth_token: ApiAuthToken, request: Request) -> None:
    """FastAPI dependency guarding state-changing endpoints with a shared secret.

    The expected token is the one ``create_app`` was handed. The check fails closed:
    when no token is configured the endpoint is disabled rather than left open.

    Args:
        api_auth_token: The configured token, or ``None`` when scrape control is disabled.
        request: Incoming request.

    Raises:
        HTTPException: 403 if no API token is configured on the server; 401 (with a
            ``WWW-Authenticate: Bearer`` challenge) if the ``Authorization`` header is
            missing, malformed, or carries the wrong token.
    """
    expected = api_auth_token.get_secret_value() if api_auth_token is not None else None
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scrape control is disabled: set API_AUTH_TOKEN",
        )

    provided = _extract_bearer_token(request.headers.get("Authorization"))
    if provided is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header: expected 'Bearer <API_AUTH_TOKEN>'",
            headers=_BEARER_CHALLENGE,
        )

    # Compare as bytes: compare_digest raises TypeError on non-ASCII str input.
    if not secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers=_BEARER_CHALLENGE,
        )
