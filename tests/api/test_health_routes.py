"""健康检查路由回归测试 — 验证 /api/health 返回 200（Issue #3）"""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_api_health_returns_200():
    """回归: GET /api/health 应返回 200 OK 和健康状态 JSON"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_api_health_no_auth_required():
    """回归: /api/health 属于公开路径，无需鉴权即可访问"""
    # 不带任何 Authorization / X-API-Key 头
    response = client.get("/api/health")
    assert response.status_code == 200
