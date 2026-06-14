"""Landing Lead API 集成测试"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_lead_limiter():
    """每个测试前后重置模块级 _lead_limiter,避免 5 req/min 状态污染。

    SlidingWindowLimiter 是模块级单例,跨测试共享;若不重置,
    后跑测试会因前面累积的计数直接 429。
    """
    from apps.api.routers import landing as landing_module
    landing_module._lead_limiter._buckets.clear()
    yield
    landing_module._lead_limiter._buckets.clear()


@pytest.fixture
def client(temp_db, monkeypatch):
    """无鉴权测试客户端 — landing POST 本就无 auth。"""
    monkeypatch.setenv("API_KEY", "")
    from apps.api.main import app
    with TestClient(app) as c:
        yield c


class TestSubmitLead:
    def test_post_valid_returns_201_and_persists(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={
                "name": "张三", "phone": "13800001234", "org": "某高速",
                "email": "z@example.com", "message": "希望了解",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "张三"
        assert "id" in body and "created_at" in body

    def test_post_missing_phone_returns_422(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={"name": "张三", "org": "某公司"},
        )
        assert resp.status_code == 422

    def test_post_bad_phone_returns_422(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={"name": "张三", "phone": "12345", "org": "某公司"},
        )
        assert resp.status_code == 422

    def test_post_rate_limited_returns_429(self, client):
        payload = {"name": "x", "phone": "13800001234", "org": "y"}
        for _ in range(5):
            assert client.post("/api/landing/leads", json=payload).status_code == 201
        # 第 6 次
        assert client.post("/api/landing/leads", json=payload).status_code == 429

    def test_post_persists_to_db(self, client):
        from apps.api.database.repositories.landing_repository import LandingRepository
        client.post(
            "/api/landing/leads",
            json={"name": "张三", "phone": "13800001234", "org": "某高速"},
        )
        assert LandingRepository().count() == 1


class TestListLeads:
    """GET 端点受 auth_middleware 保护。这里直接 monkeypatch auth.API_KEY,
    避免 importlib.reload(main) 引发的后台 scheduler 残留问题(会污染后续测试)。"""

    @pytest.fixture
    def authed_client(self, temp_db, monkeypatch):
        from apps.api.main import app
        from apps.api.core import auth as auth_mod
        monkeypatch.setattr(auth_mod, "API_KEY", "test-key")
        with TestClient(app) as c:
            yield c

    def test_list_no_token_returns_401(self, authed_client):
        resp = authed_client.get("/api/landing/leads")
        assert resp.status_code == 401

    def test_list_with_token_returns_paginated(self, authed_client):
        # 用合法手机号(11 位,1[3-9] 开头)
        phones = ["13800001234", "13812345678"]
        for i, phone in enumerate(phones):
            r = authed_client.post(
                "/api/landing/leads",
                json={"name": f"u{i}", "phone": phone, "org": "y"},
                headers={"X-API-Key": "test-key"},
            )
            assert r.status_code == 201, r.text
        resp = authed_client.get(
            "/api/landing/leads",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert "leads" in data
