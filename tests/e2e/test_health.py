"""健康检查与基础 API 测试"""

from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_stats():
    response = client.get("/api/audit/stats/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_trips" in data


def test_process_action_validation():
    response = client.post("/api/audit/suspect/999/process", json={"action": "INVALID"})
    assert response.status_code == 422
