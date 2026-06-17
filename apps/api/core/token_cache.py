"""内存 Token 缓存 — refresh token 存储和黑名单管理"""

import threading
import time

DEFAULT_REFRESH_TTL = 3600
DEFAULT_BLACKLIST_TTL = 1800
DEFAULT_VERIFY_TTL = 60


class TokenCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._refresh_tokens: dict[str, tuple[str, float]] = {}
        self._blacklist: dict[str, float] = {}
        self._verified: dict[str, float] = {}

    def set_refresh_token(self, session_id: str, token: str, ttl: int = DEFAULT_REFRESH_TTL):
        with self._lock:
            self._refresh_tokens[session_id] = (token, time.time() + ttl)

    def get_refresh_token(self, session_id: str) -> str | None:
        with self._lock:
            self._cleanup()
            entry = self._refresh_tokens.get(session_id)
            if entry is None:
                return None
            token, expiry = entry
            if time.time() > expiry:
                del self._refresh_tokens[session_id]
                return None
            return token

    def remove_refresh_token(self, session_id: str):
        with self._lock:
            self._refresh_tokens.pop(session_id, None)

    def blacklist(self, token: str, ttl: int = DEFAULT_BLACKLIST_TTL):
        with self._lock:
            self._blacklist[token] = time.time() + ttl

    def is_blacklisted(self, token: str) -> bool:
        with self._lock:
            self._cleanup()
            expiry = self._blacklist.get(token)
            if expiry is None:
                return False
            if time.time() > expiry:
                del self._blacklist[token]
                return False
            return True

    def is_verified(self, token: str) -> bool:
        with self._lock:
            self._cleanup()
            expiry = self._verified.get(token)
            if expiry is None:
                return False
            if time.time() > expiry:
                del self._verified[token]
                return False
            return True

    def mark_verified(self, token: str, ttl: int = DEFAULT_VERIFY_TTL):
        with self._lock:
            self._verified[token] = time.time() + ttl

    def invalidate_verification(self, token: str):
        with self._lock:
            self._verified.pop(token, None)

    def _cleanup(self):
        now = time.time()
        expired_rt = [k for k, (_, exp) in self._refresh_tokens.items() if now > exp]
        for k in expired_rt:
            del self._refresh_tokens[k]
        expired_bl = [k for k, exp in self._blacklist.items() if now > exp]
        for k in expired_bl:
            del self._blacklist[k]
        expired_v = [k for k, exp in self._verified.items() if now > exp]
        for k in expired_v:
            del self._verified[k]


token_cache = TokenCache()
