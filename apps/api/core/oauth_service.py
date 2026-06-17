"""OAuth 平台 HTTP 客户端"""

import base64
import logging

import httpx

from apps.api.core.config import (
    AUTH_JWT_CLIENT_ID,
    AUTH_JWT_CLIENT_SECRET,
    AUTH_JWT_SERVICE_BASE_URL,
)

logger = logging.getLogger(__name__)


class OAuthService:
    def __init__(self):
        self._base_url = AUTH_JWT_SERVICE_BASE_URL.rstrip("/")

    def _basic_auth_header(self) -> str:
        auth = f"{AUTH_JWT_CLIENT_ID}:{AUTH_JWT_CLIENT_SECRET}"
        encoded = base64.b64encode(auth.encode()).decode()
        return f"Basic {encoded}"

    async def exchange_token(self, code: str) -> dict:
        url = f"{self._base_url}/exchange?code={code}"
        headers = {"Authorization": self._basic_auth_header()}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers)
            data = resp.json()
        if data.get("code") != 200 or not data.get("data"):
            raise RuntimeError(data.get("msg", "Token exchange failed"))
        inner = data["data"]
        return {"accessToken": inner["accessToken"], "refreshToken": inner["refreshToken"]}

    async def refresh_token(self, refresh_token: str) -> str:
        url = f"{self._base_url}/refresh?refreshToken={refresh_token}"
        headers = {"Authorization": self._basic_auth_header()}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers)
            data = resp.json()
        if data.get("code") != 200 or not data.get("data"):
            raise RuntimeError(data.get("msg", "Token refresh failed"))
        return data["data"]["accessToken"]

    async def revoke_token(self, token: str) -> None:
        url = f"{self._base_url}/revoke?token={token}"
        headers = {"Authorization": self._basic_auth_header()}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, headers=headers)
        except Exception as e:
            logger.warning("Token revoke call failed (non-critical): %s", e)

    async def get_user_info(self, access_token: str) -> dict:
        url = f"{self._base_url}/userInfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers)
            data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(data.get("msg", "Failed to get user info"))
        return data["data"]


oauth_service = OAuthService()
