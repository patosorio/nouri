from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from config import settings
from db.session import get_db
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from services.profile_service import ProfileService
from sqlalchemy.ext.asyncio import AsyncSession

# FastAPI reads these once; B008 forbids the call in a parameter default.
_db = Depends(get_db)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        base = (settings.supabase_url or "").strip().strip('"').strip("'")
        if base.startswith("SUPABASE_URL="):
            # Common .env mistake: value includes the key name.
            base = base.split("=", 1)[1].strip().strip('"').strip("'")
        if not base.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": {
                        "code": "AUTH_MISCONFIGURED",
                        "message": (
                            "SUPABASE_URL must be an https URL "
                            "(e.g. https://<project>.supabase.co), not empty "
                            "and not prefixed with SUPABASE_URL="
                        ),
                    }
                },
            )
        jwks_url = f"{base.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def reset_jwks_client() -> None:
    """Force JWKS refresh (e.g. after signature verification failure)."""
    global _jwks_client
    _jwks_client = None


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    tier: str


def _unauthorized(message: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "UNAUTHORIZED", "message": message}},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise _unauthorized("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Invalid Authorization header")
    return token


def _decode_access_token(token: str) -> dict[str, object]:
    client = _get_jwks_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
            issuer=settings.supabase_jwt_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWKClientError:
        reset_jwks_client()
        client = _get_jwks_client()
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated",
                issuer=settings.supabase_jwt_issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            raise _unauthorized("Invalid or expired token") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc


async def get_current_user(
    request: Request,
    db: AsyncSession = _db,
) -> CurrentUser:
    token = _extract_bearer_token(request)
    claims = _decode_access_token(token)

    raw_sub = claims.get("sub")
    if not isinstance(raw_sub, str):
        raise _unauthorized("Token missing subject")

    try:
        user_id = UUID(raw_sub)
    except ValueError as exc:
        raise _unauthorized("Token subject is not a valid UUID") from exc

    email_claim = claims.get("email")
    email = email_claim if isinstance(email_claim, str) else ""

    profile = await ProfileService().ensure_profile(user_id, db)
    tier_value = profile.tier
    tier = tier_value.value if hasattr(tier_value, "value") else str(tier_value)

    request.state.user_id = user_id
    return CurrentUser(id=user_id, email=email, tier=tier)


_current_user = Depends(get_current_user)


async def get_tier(
    current_user: CurrentUser = _current_user,
) -> str:
    return current_user.tier


async def require_paid_tier(
    current_user: CurrentUser = _current_user,
) -> CurrentUser:
    # ERD: user_tier_enum = free | pro. Phase 2 prompt said "paid" — see missing.txt.
    if current_user.tier != "pro":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "TIER_GATE",
                    "message": "This feature requires a paid plan.",
                }
            },
        )
    return current_user
