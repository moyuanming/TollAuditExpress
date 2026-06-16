"""Audit API 路由集成测试"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db, mock_ai_client, monkeypatch):
    """创建测试客户端（无鉴权）"""
    monkeypatch.setenv("API_KEY", "")
    from apps.api.main import app

    with TestClient(app) as c:
        yield c


class TestStatsAndTrips:
    def test_get_stats(self, client):
        resp = client.get("/api/audit/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trips"] == 0
        assert data["verified_trips"] == 0

    def test_get_trips_empty(self, client):
        resp = client.get("/api/audit/trips")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_get_trips_with_data(self, client):
        from apps.api.database.repositories.trip_repository import TripRepository

        TripRepository().save_trip(
            {
                "passid": "API001",
                "entry_time": "2025-06-15 08:00:00",
            }
        )

        resp = client.get("/api/audit/trips")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["trips"][0]["passid"] == "API001"

    def test_get_trip_not_found(self, client):
        resp = client.get("/api/audit/trip/NONEXISTENT")
        assert resp.status_code == 404

    def test_get_trip_detail(self, client):
        from apps.api.database.repositories.trip_repository import TripRepository

        TripRepository().save_trip(
            {
                "passid": "API002",
                "entry_station_name": "test_station",
            }
        )

        resp = client.get("/api/audit/trip/API002")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_station_name"] == "test_station"


class TestDetectEndpoints:
    def test_detect_passenger_obu_not_found(self, client):
        resp = client.post("/api/audit/detect/passenger-obu", json={"passid": "NOEXIST"})
        assert resp.status_code == 404

    def test_detect_passenger_obu(self, client):
        from apps.api.database.repositories.trip_repository import TripRepository

        TripRepository().save_trip(
            {
                "passid": "DETECT001",
                "entry_vehicle_type": 1,
                "entry_image_trans": "http://fake/trans.jpg",
            }
        )

        resp = client.post("/api/audit/detect/passenger-obu", json={"passid": "DETECT001"})
        assert resp.status_code == 200
        data = resp.json()
        assert "is_suspicious" in data

    def test_detect_entry_exit_not_found(self, client):
        resp = client.post("/api/audit/detect/entry-exit", json={"passid": "NOEXIST"})
        assert resp.status_code == 404

    def test_detect_entry_exit(self, client):
        from apps.api.database.repositories.trip_repository import TripRepository

        TripRepository().save_trip(
            {
                "passid": "DETECT002",
                "entry_image_license": "http://fake/entry.jpg",
                "exit_image_license": "http://fake/exit.jpg",
            }
        )

        resp = client.post("/api/audit/detect/entry-exit", json={"passid": "DETECT002"})
        assert resp.status_code == 200
        data = resp.json()
        assert "_comparison_success" in data


class TestAuth:
    def test_no_auth_when_empty(self, client):
        """client fixture already sets API_KEY=''"""
        resp = client.get("/api/audit/stats/overview")
        assert resp.status_code == 200

    def test_auth_required(self, temp_db, mock_ai_client, monkeypatch):
        """测试 API_KEY 设置后需要鉴权"""
        monkeypatch.setattr("apps.api.core.auth.API_KEY", "secret")
        from apps.api.main import app

        app.state.truck_detector = None
        app.state.entry_exit_matcher = None
        with TestClient(app) as c:
            resp = c.get("/api/audit/stats/overview")
            assert resp.status_code == 401

            resp = c.get("/api/audit/stats/overview", headers={"X-API-Key": "secret"})
            assert resp.status_code == 200

    def test_health_bypasses_auth(self, temp_db, monkeypatch):
        """测试健康检查绕过鉴权"""
        monkeypatch.setattr("apps.api.core.auth.API_KEY", "secret")
        from apps.api.main import app

        with TestClient(app) as c:
            resp = c.get("/api/health")
            assert resp.status_code == 200

    def test_doris_health_endpoint(self, client):
        """GET /api/health/doris 返回详细 Doris 健康信息"""
        resp = client.get("/api/health/doris")
        assert resp.status_code == 200
        data = resp.json()
        # 测试环境：get_connection 走 SQLite，source_db 连接失败 → "degraded"
        assert data["status"] in ("ok", "degraded", "error")
        assert "target_db" in data
        assert "source_db" in data
        assert "pool" in data
        assert data["pool"]["max_size"] > 0
        # target_db 走 SQLite wrapper，应连接成功
        assert data["target_db"]["connected"] is True
        assert "table_counts" in data["target_db"]
        assert "audit_trips" in data["target_db"]["table_counts"]


class TestSuspects:
    def test_get_suspects_empty(self, client):
        resp = client.get("/api/audit/suspects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_get_suspect_not_found(self, client):
        resp = client.get("/api/audit/suspect/999")
        assert resp.status_code == 404
