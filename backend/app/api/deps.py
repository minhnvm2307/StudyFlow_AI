"""FastAPI dependency providers."""
from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from inspect import isawaitable

import asyncpg
from fastapi import Depends, HTTPException, Query, Request
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings
from app.db import repository
from app.db.pg_pool import get_pool

_current_user_id: ContextVar[str | None] = ContextVar("studyflow_current_user_id", default=None)

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/mock",
    "/api/documents/mock-upload",
}
PUBLIC_API_PREFIXES = ("/api/dev/",)


def get_pool_dep() -> asyncpg.Pool:
    return get_pool()


def is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


def create_access_token(user_id: str) -> tuple[str, int]:
    expires_in = settings.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    token = jwt.encode(
        {"sub": user_id, "exp": expires_at},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, expires_in


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Access token expired") from exc
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return user_id


async def _resolve_pool(request: Request) -> asyncpg.Pool:
    override = request.app.dependency_overrides.get(get_pool)
    provider = override or get_pool
    pool = provider()
    if isawaitable(pool):
        pool = await pool
    return pool


async def authenticate_api_request(request: Request) -> Token[str | None] | None:
    path = request.url.path
    if request.method.upper() == "OPTIONS":
        return None
    if not path.startswith("/api") or is_public_api_path(path):
        return None

    authorization = request.headers.get("Authorization", "").strip()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = decode_access_token(token.strip())
    pool = await _resolve_pool(request)
    profile = await repository.get_profile(pool, user_id)
    if not profile:
        raise HTTPException(status_code=401, detail="Invalid access token")

    request.state.current_user_id = user_id
    return _current_user_id.set(user_id)


def clear_current_user(token: Token[str | None] | None) -> None:
    if token is not None:
        _current_user_id.reset(token)


def current_user_id() -> str:
    user_id = _current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def get_current_user(
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool_dep),
) -> str:
    """Backward-compatible dependency wrapper for authenticated routes."""
    del user_id, pool
    return current_user_id()
