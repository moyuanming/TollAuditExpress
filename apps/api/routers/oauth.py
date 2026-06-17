"""OAuth 路由"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query

from apps.api.core.config import AUTH_ENABLED, AUTH_JWT_PUBLIC_KEY, AUTH_LOGIN_URL
from apps.api.core.jwt_util import JwtExpiredError, JwtInvalidError, decode_and_validate, parse_payload_unsafe
from apps.api.core.oauth_service import oauth_service
from apps.api.core.token_cache import token_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oauth", tags=["oauth"])


@router.post("/callback")
async def oauth_callback(code: str = Query(...)):
    if not code:
        raise HTTPException(status_code=400, detail="授权码为空")

    try:
        tokens = await oauth_service.exchange_token(code)
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))
    access_token = tokens["accessToken"]
    refresh_token = tokens["refreshToken"]

    try:
        payload = decode_and_validate(access_token, AUTH_JWT_PUBLIC_KEY)
    except (JwtExpiredError, JwtInvalidError) as e:
        logger.error("Token validation failed after exchange: %s", e)
        raise HTTPException(status_code=401, detail="Token 验证失败")

    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Token 格式错误")

    token_cache.set_refresh_token(str(session_id), refresh_token)
    return {"code": 200, "data": {"accessToken": access_token}, "msg": "登录成功"}


@router.post("/logout")
async def oauth_logout(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ")
    if not token:
        raise HTTPException(status_code=400, detail="缺少 Token")

    try:
        await oauth_service.revoke_token(token)
    except Exception as e:
        logger.warning("Revoke failed: %s", e)

    token_cache.blacklist(token)
    payload = parse_payload_unsafe(token)
    session_id = payload.get("session_id")
    if session_id:
        token_cache.remove_refresh_token(str(session_id))

    return {"code": 200, "msg": "登出成功"}


@router.get("/config")
async def oauth_config():
    return {
        "code": 200,
        "data": {
            "authEnabled": AUTH_ENABLED,
            "loginUrl": AUTH_LOGIN_URL if AUTH_ENABLED else "",
        },
    }
