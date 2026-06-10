"""统一鉴权中间件 — 支持 JWT Bearer Token 和静态 API Key"""

import logging

from fastapi import Request
from starlette.responses import JSONResponse

from apps.api.core.config import API_KEY, AUTH_ENABLED, AUTH_JWT_PUBLIC_KEY
from apps.api.core.jwt_util import decode_and_validate, parse_payload_unsafe, JwtExpiredError, JwtInvalidError
from apps.api.core.token_cache import token_cache

logger = logging.getLogger(__name__)

PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/assets/")
PUBLIC_EXACT = ("/", "")
OAUTH_PREFIX = "/api/oauth"


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    if path.startswith(OAUTH_PREFIX):
        return await call_next(request)

    if AUTH_ENABLED:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await _handle_jwt_auth(request, call_next, auth_header)

    return await _handle_api_key_auth(request, call_next)


async def _handle_jwt_auth(request, call_next, auth_header):
    token = auth_header[7:]

    if token_cache.is_blacklisted(token):
        return JSONResponse(status_code=401, content={"detail": "Token已被注销"})

    try:
        decode_and_validate(token, AUTH_JWT_PUBLIC_KEY)
    except JwtExpiredError:
        return await _try_refresh_and_continue(request, call_next, token)
    except JwtInvalidError:
        return JSONResponse(status_code=401, content={"detail": "Token验证无效"})

    # 定期向平台验证 token 是否仍有效（处理用户在平台端退出登录的场景）
    if not token_cache.is_verified(token):
        from apps.api.core.oauth_service import oauth_service
        try:
            await oauth_service.get_user_info(token)
            token_cache.mark_verified(token)
        except Exception:
            token_cache.blacklist(token)
            return JSONResponse(status_code=401, content={"detail": "Token已失效，请重新登录"})

    return await call_next(request)


async def _try_refresh_and_continue(request, call_next, token):
    payload = parse_payload_unsafe(token)
    session_id = payload.get("session_id")
    if not session_id:
        return JSONResponse(status_code=401, content={"detail": "Token格式错误"})

    refresh_token = token_cache.get_refresh_token(str(session_id))
    if not refresh_token:
        return JSONResponse(status_code=401, content={"detail": "Token已过期，请重新登录"})

    from apps.api.core.oauth_service import oauth_service

    try:
        new_token = await oauth_service.refresh_token(refresh_token)
    except Exception as e:
        logger.error("Token refresh failed: %s", e)
        return JSONResponse(status_code=401, content={"detail": "Token刷新失败，请重新登录"})

    _patch_authorization_header(request, new_token)
    response = await call_next(request)
    response.headers["X-New-Access-Token"] = new_token
    return response


async def _handle_api_key_auth(request, call_next):
    if not API_KEY:
        return await call_next(request)
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key:
        api_key = request.headers.get("X-API-Key", "")
    if api_key != API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


def _patch_authorization_header(request: Request, new_token: str):
    headers = list(request.scope["headers"])
    new_auth = f"Bearer {new_token}".encode()
    headers = [(k, new_auth) if k == b"authorization" else (k, v) for k, v in headers]
    if b"authorization" not in [k for k, _ in headers]:
        headers.append((b"authorization", new_auth))
    request.scope["headers"] = headers
