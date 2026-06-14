"""简单内存限流器 — 滑动窗口,按 key(通常为 IP)计数。

仅供单进程使用,重启会丢失计数。多副本部署需替换为 Redis。
"""
import time
from collections import deque
from threading import Lock
from typing import Dict, Deque


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """返回 True 表示允许(并在桶里加 1),False 表示被限流。"""
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            # 弹出窗口外的旧戳
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True
