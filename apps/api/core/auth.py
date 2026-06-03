"""API Key 鉴权中间件"""

import logging
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.core.config import API_KEY

logger = logging.getLogger(__name__)

EXCLUDED_PATHS = ["/health", "/docs", "/openapi.json", "/redoc"]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not API_KEY:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in EXCLUDED_PATHS):
            return await call_next(request)

        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.headers.get("X-API-Key", "")

        if token != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

        return await call_next(request)
