"""POST /api/audit/detect/entry-exit/llm 路由测试 — 覆盖成功、参数缺失、依赖错误的 HTTP 状态码。"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setenv('API_KEY', '')
    from apps.api.main import app
    app.state.truck_detector = None
    app.state.entry_exit_matcher = None
    app.state.aggregation_tasks = {}
    with TestClient(app) as c:
        yield c


class TestDetectEntryExitLlmRoute:
    def test_missing_passid_returns_422(self, client):
        resp = client.post('/api/audit/detect/entry-exit/llm', json={})
        assert resp.status_code == 422

    def test_trip_not_found_returns_404(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value={'error': 'trip_not_found'},
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'NOPE'},
            )
        assert resp.status_code == 404
        assert resp.json()['detail']['error'] == 'trip_not_found'

    def test_image_url_missing_returns_400(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value={'error': 'image_url_missing', 'field': 'entry_image_license'},
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'P1'},
            )
        assert resp.status_code == 400
        assert resp.json()['detail']['error'] == 'image_url_missing'

    def test_maas_unavailable_returns_502(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value={'error': 'maas_unavailable', 'detail': 'timeout'},
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'P2'},
            )
        assert resp.status_code == 502
        assert resp.json()['detail']['error'] == 'maas_unavailable'

    def test_parse_error_returns_502(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value={'error': 'parse_error', 'detail': 'missing fields'},
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'P3'},
            )
        assert resp.status_code == 502

    def test_image_download_failed_returns_502(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value={
                'error': 'image_download_failed',
                'entry_ok': True,
                'exit_ok': False,
            },
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'P4'},
            )
        assert resp.status_code == 502

    def test_happy_path_returns_full_payload(self, client):
        success = {
            'passid': 'P_OK',
            'is_same_vehicle': True,
            'confidence': 0.91,
            'reason': '车牌号一致',
            'entry_image_url': 'http://x/entry.jpg',
            'exit_image_url': 'http://x/exit.jpg',
            'model': 'qwen2.5-vl-72b',
            'elapsed_ms': 1234,
            'plate_match': None,
            'plate_recognized_entry': None,
            'plate_recognized_exit': None,
        }
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
            return_value=success,
        ):
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': 'P_OK'},
            )
        assert resp.status_code == 200
        assert resp.json() == success

    def test_whitespace_passid_returns_400(self, client):
        with patch(
            'apps.api.routers.audit.compare_vehicles_by_passid',
        ) as mock_call:
            resp = client.post(
                '/api/audit/detect/entry-exit/llm',
                json={'passid': '   '},
            )
        assert resp.status_code == 400
        assert 'passid required' in resp.json()['detail']
        mock_call.assert_not_called()
