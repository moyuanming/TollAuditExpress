"""简单内存限流器测试"""
import time

from apps.api.core.rate_limit import SlidingWindowLimiter


def test_first_request_allowed():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    assert lim.allow("1.1.1.1") is True


def test_under_limit_allowed():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert lim.allow("1.1.1.1") is True


def test_over_limit_rejected():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        lim.allow("1.1.1.1")
    assert lim.allow("1.1.1.1") is False


def test_different_keys_independent():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        lim.allow("1.1.1.1")
    assert lim.allow("2.2.2.2") is True


def test_window_expiry(monkeypatch):
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    base = time.time()
    monkeypatch.setattr("apps.api.core.rate_limit.time.time", lambda: base)
    for _ in range(5):
        lim.allow("1.1.1.1")
    # 推进 61s,窗口已滑出
    monkeypatch.setattr("apps.api.core.rate_limit.time.time", lambda: base + 61)
    assert lim.allow("1.1.1.1") is True
