"""FastAPI auth dependencies."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from src.auth.models import UserProfile
from src.auth.service import get_auth_service


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> UserProfile | None:
    token = _extract_bearer(authorization)
    if not token:
        return None
    svc = get_auth_service()
    user_id = svc.resolve_user_id(token)
    if not user_id:
        return None
    return svc.get_user_profile(user_id)


async def get_current_user(
    user: Annotated[UserProfile | None, Depends(get_optional_user)],
) -> UserProfile:
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或 token 已失效")
    return user
