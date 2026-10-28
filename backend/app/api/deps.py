from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request

from app.config import Settings, get_settings
from app.db import get_db

__all__ = ["get_db", "get_settings", "require_admin", "read_limited_body", "client_key"]


def require_admin(authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> str:
    expected = f"Bearer {settings.admin_token}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="admin token required")
    return "admin"


async def read_limited_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"payload exceeds {limit} bytes")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"payload exceeds {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def client_key(request: Request) -> str:
    """Rate-limit key for the client address. Hashed in memory, never stored or logged."""
    return request.client.host if request.client else "unknown"
