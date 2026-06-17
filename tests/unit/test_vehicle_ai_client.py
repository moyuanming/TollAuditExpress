"""vehicle-ai-service HTTP 客户端单元测试。

通过 mock `httpx.Client` 注入 `MockTransport`,避免真实网络请求。
"""

import json
from unittest.mock import patch

import httpx

from apps.api.core.vehicle_ai_client import VehicleAIClient, get_client


def _client_with(handler):
    """构造一个使用 mock transport 的 VehicleAIClient。"""
    transport = httpx.MockTransport(handler)
    return VehicleAIClient(base_url="http://mock-vehicle-ai:8081", timeout_s=5.0), transport


# ============================================================
# compare()
# ============================================================


class TestCompare:
    def test_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "is_same_vehicle": True,
                "confidence": 0.92,
                "reason": "车牌号一致",
                "model": "qwen2.5-vl-72b",
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client", return_value=httpx.Client(transport=transport)):
            result = client.compare("http://a", "http://b")
        assert result == {
            "is_same_vehicle": True,
            "confidence": 0.92,
            "reason": "车牌号一致",
            "model": "qwen2.5-vl-72b",
        }

    def test_passes_all_9_metadata_fields(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "is_same_vehicle": True, "confidence": 0.9, "reason": "ok", "model": "m"
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client", return_value=httpx.Client(transport=transport)):
            client.compare(
                "http://a", "http://b",
                entry_vehicle_id="京A1",
                exit_vehicle_id="京A1",
                entry_obu_id="OBU1",
                exit_obu_id="OBU1",
                entry_color="blue",
                exit_color="blue",
                entry_visual_type="truck",
                exit_visual_type="truck",
                fingerprint_sim=0.88,
            )
        body = captured["body"]
        assert body["image_url_a"] == "http://a"
        assert body["image_url_b"] == "http://b"
        for k in ("entry_vehicle_id", "exit_vehicle_id", "entry_obu_id", "exit_obu_id",
                  "entry_color", "exit_color", "entry_visual_type", "exit_visual_type",
                  "fingerprint_sim"):
            assert k in body, f"missing {k} in body: {body}"

    def test_filters_none_metadata(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "is_same_vehicle": True, "confidence": 0.9, "reason": "ok", "model": "m"
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client", return_value=httpx.Client(transport=transport)):
            client.compare("http://a", "http://b", entry_vehicle_id="京A1")
        body = captured["body"]
        assert "exit_vehicle_id" not in body
        assert "entry_obu_id" not in body
        assert "fingerprint_sim" not in body
        assert body["entry_vehicle_id"] == "京A1"

    def test_http_timeout_returns_service_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            result = client.compare("http://a", "http://b")
        assert result["error"] == "service_unavailable"
        assert "url" in result
        assert result["url"] == "http://mock-vehicle-ai:8081/api/v1/vehicle/compare"

    def test_non_200_with_json_detail(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "image_url_a invalid"})

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            result = client.compare("http://a", "http://b")
        assert result["error"] == "service_unavailable"
        assert result["detail"] == "image_url_a invalid"

    def test_non_json_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            result = client.compare("http://a", "http://b")
        assert result["error"] == "parse_error"
        assert "non-JSON" in result["detail"]


# ============================================================
# entry_exit()
# ============================================================


class TestEntryExit:
    def test_payload_field_names(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            captured["path"] = request.url.path
            return httpx.Response(200, json={
                "is_suspicious": False, "fingerprint_sim": 0.95,
                "comparison_success": True,
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            result = client.entry_exit("http://entry", "http://exit")
        body = captured["body"]
        assert body == {"entry_image_url": "http://entry", "exit_image_url": "http://exit"}
        assert captured["path"] == "/api/v1/vehicle/entry-exit"
        assert result["is_suspicious"] is False


# ============================================================
# truck_obu()
# ============================================================


class TestTruckObu:
    def test_declared_default_is_1(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "is_suspicious": False, "fraud_type": None,
                "visual_vehicle_type": "passenger", "confidence": 0.85,
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            client.truck_obu("http://img")
        assert captured["body"]["declared_vehicle_type"] == 1
        assert captured["body"]["image_url"] == "http://img"

    def test_declared_explicit_2(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "is_suspicious": True, "fraud_type": "TRUCK_USES_PASSENGER_OBU",
                "visual_vehicle_type": "truck", "confidence": 0.95,
            })

        client, transport = _client_with(handler)
        with patch("apps.api.core.vehicle_ai_client.httpx.Client",
                   return_value=httpx.Client(transport=transport)):
            client.truck_obu("http://img", declared_vehicle_type=2)
        assert captured["body"]["declared_vehicle_type"] == 2
        assert captured["body"]["image_url"] == "http://img"


# ============================================================
# get_client() 单例 + base_url 规范化
# ============================================================


class TestGetClient:
    def test_singleton(self, monkeypatch):
        """两次 get_client() 拿到同一实例,第二次不再构造。"""
        monkeypatch.setattr("apps.api.core.vehicle_ai_client._client", None)
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2

    def test_base_url_trailing_slash_stripped(self):
        c = VehicleAIClient(base_url="http://example.com:8081/", timeout_s=10.0)
        assert c.base_url == "http://example.com:8081"

    def test_base_url_no_slash_unchanged(self):
        c = VehicleAIClient(base_url="http://example.com:8081", timeout_s=10.0)
        assert c.base_url == "http://example.com:8081"
