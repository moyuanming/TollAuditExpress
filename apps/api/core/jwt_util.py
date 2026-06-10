"""JWT 解析与验证工具"""

import base64
import json
import logging

logger = logging.getLogger(__name__)

try:
    import jwt
    from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError, InvalidTokenError
    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False


def decode_and_validate(token: str, public_key_pem: str) -> dict:
    """验证 JWT 签名和过期时间，返回 payload。"""
    if not _HAS_PYJWT:
        raise RuntimeError("PyJWT not installed; run: pip install PyJWT[crypto]")
    try:
        return jwt.decode(token, public_key_pem, algorithms=["RS256", "RS384", "RS512"])
    except ExpiredSignatureError:
        raise JwtExpiredError("Token expired")
    except InvalidSignatureError:
        raise JwtInvalidError("Invalid token signature")
    except InvalidTokenError as e:
        raise JwtInvalidError(str(e))


def parse_payload_unsafe(token: str) -> dict:
    """不验签，仅解码 JWT payload（用于提取过期 token 中的 session_id）。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded)
    except Exception as e:
        logger.warning("Failed to parse JWT payload: %s", e)
        return {}


class JwtExpiredError(Exception):
    pass


class JwtInvalidError(Exception):
    pass
