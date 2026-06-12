"""Doris 车辆查询路由集成测试 - 通过 monkeypatch 替换服务避免真实 DB 连接"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db, mock_ai_client, monkeypatch):
    monkeypatch.setenv('API_KEY', '')
    from apps.api.main import app
    app.state.truck_detector = None
    app.state.entry_exit_matcher = None
    app.state.aggregation_tasks = {}
    with TestClient(app) as c:
        yield c


def _patch_query(monkeypatch, rows, total):
    from apps.api.routers import audit
    monkeypatch.setattr(
        audit, 'doris_query_trips',
        lambda filters, limit, offset: (rows, total),
    )


def _patch_detail(monkeypatch, detail):
    from apps.api.routers import audit
    monkeypatch.setattr(
        audit, 'doris_get_trip_detail',
        lambda passid: detail,
    )


class TestDorisVehiclesList:
    """GET /api/audit/doris/vehicles - 列表"""

    def test_basic_structure(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[
            {
                'passid': 'P001',
                'entry_time': '2026-05-01T08:00:00',
                'entry_station_name': '北京南',
                'entry_vehicle_id': '京A12345',
                'entry_vehicle_color': '1',
                'entry_vehicle_type': 1,
                'entry_obu_id': 'OBU1',
                'exit_time': '2026-05-01T10:00:00',
                'exit_station_name': '天津',
                'exit_vehicle_id': '京A12345',
                'exit_vehicle_color': '1',
                'exit_vehicle_type': 1,
                'exit_obu_id': 'OBU1',
                'gantry_count': 3,
            }
        ], total=1)

        resp = client.get('/api/audit/doris/vehicles?vehicle_id=京A12345')
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 1
        assert data['limit'] == 20
        assert data['offset'] == 0
        assert len(data['trips']) == 1
        assert data['trips'][0]['passid'] == 'P001'
        assert data['trips'][0]['gantry_count'] == 3
        assert 'risk_score' not in data['trips'][0]
        assert 'audit_status' not in data['trips'][0]
        assert 'entry_visual_type' not in data['trips'][0]

    def test_no_detection_fields_in_response(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[{
            'passid': 'P', 'gantry_count': 0
        }], total=1)
        resp = client.get('/api/audit/doris/vehicles')
        assert resp.status_code == 200
        trip = resp.json()['trips'][0]
        for forbidden in ('risk_score', 'audit_status',
                          'entry_visual_type', 'exit_visual_type', 'fingerprint_sim'):
            assert forbidden not in trip, f"{forbidden} should not be in raw trip response"

    def test_vehicle_id_match_exact_passes_through(self, client, monkeypatch):
        captured = {}
        def fake_query(filters, limit, offset):
            captured['filters'] = filters
            captured['limit'] = limit
            captured['offset'] = offset
            return [], 0
        from apps.api.routers import audit
        monkeypatch.setattr(audit, 'doris_query_trips', fake_query)

        resp = client.get('/api/audit/doris/vehicles?vehicle_id=京A12345&vehicle_id_match=exact')
        assert resp.status_code == 200
        assert captured['filters']['vehicle_id_match'] == 'exact'
        assert captured['filters']['vehicle_id'] == '京A12345'

    def test_vehicle_id_match_prefix_passes_through(self, client, monkeypatch):
        captured = {}
        def fake_query(filters, limit, offset):
            captured['filters'] = filters
            return [], 0
        from apps.api.routers import audit
        monkeypatch.setattr(audit, 'doris_query_trips', fake_query)

        resp = client.get('/api/audit/doris/vehicles?vehicle_id=京A&vehicle_id_match=prefix')
        assert resp.status_code == 200
        assert captured['filters']['vehicle_id_match'] == 'prefix'

    def test_vehicle_id_match_contains_passes_through(self, client, monkeypatch):
        captured = {}
        def fake_query(filters, limit, offset):
            captured['filters'] = filters
            return [], 0
        from apps.api.routers import audit
        monkeypatch.setattr(audit, 'doris_query_trips', fake_query)

        resp = client.get('/api/audit/doris/vehicles?vehicle_id=123&vehicle_id_match=contains')
        assert resp.status_code == 200
        assert captured['filters']['vehicle_id_match'] == 'contains'

    def test_invalid_vehicle_id_match_returns_400(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[], total=0)
        resp = client.get('/api/audit/doris/vehicles?vehicle_id_match=hax')
        assert resp.status_code == 400
        assert 'vehicle_id_match' in resp.json()['detail']

    def test_start_after_end_returns_400(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[], total=0)
        resp = client.get(
            '/api/audit/doris/vehicles?start_time=2026-06-01T00:00:00&end_time=2026-05-01T00:00:00'
        )
        assert resp.status_code == 400
        assert 'start_time' in resp.json()['detail']

    def test_invalid_order_by_returns_400(self, client, monkeypatch):
        """SQL 注入防御：非法排序列直接 400"""
        _patch_query(monkeypatch, rows=[], total=0)
        resp = client.get('/api/audit/doris/vehicles?order_by=entry_time;DROP%20TABLE--')
        assert resp.status_code == 400
        assert 'order_by' in resp.json()['detail']

    def test_invalid_order_direction_returns_400(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[], total=0)
        resp = client.get('/api/audit/doris/vehicles?order=sideways')
        assert resp.status_code == 400
        assert 'order' in resp.json()['detail']

    def test_min_gantry_greater_than_max_returns_400(self, client, monkeypatch):
        _patch_query(monkeypatch, rows=[], total=0)
        resp = client.get('/api/audit/doris/vehicles?min_gantry_count=10&max_gantry_count=2')
        assert resp.status_code == 400

    def test_service_unexpected_error_returns_500(self, client, monkeypatch):
        """服务层抛非 ValueError 异常时路由翻译为 500"""
        from apps.api.routers import audit
        def fake_query(filters, limit, offset):
            raise RuntimeError('doris down')
        monkeypatch.setattr(audit, 'doris_query_trips', fake_query)

        resp = client.get('/api/audit/doris/vehicles')
        assert resp.status_code == 500
        assert 'doris' in resp.json()['detail'].lower()


class TestDorisVehicleDetail:
    """GET /api/audit/doris/vehicle/{passid}/full - 详情"""

    def test_returns_404_when_service_returns_none(self, client, monkeypatch):
        _patch_detail(monkeypatch, None)
        resp = client.get('/api/audit/doris/vehicle/NONEXIST/full')
        assert resp.status_code == 404

    def test_detail_includes_gantry_records_and_images(self, client, monkeypatch):
        _patch_detail(monkeypatch, {
            'passid': 'P1',
            'entry_time': '2026-05-01T08:00:00',
            'entry_station_name': 'S1',
            'entry_vehicle_id': '京A12345',
            'entry_vehicle_color': '1',
            'entry_vehicle_type': 1,
            'entry_obu_id': 'OBU1',
            'entry_lane_id': 'L1',
            'entry_image_license': 'http://x/lic.jpg',
            'entry_image_trans': 'http://x/trans.jpg',
            'exit_time': '2026-05-01T10:00:00',
            'exit_station_name': 'S2',
            'exit_vehicle_id': '京A12345',
            'exit_vehicle_color': '1',
            'exit_vehicle_type': 1,
            'exit_obu_id': 'OBU1',
            'exit_lane_id': 'L2',
            'exit_image_license': 'http://x/lic2.jpg',
            'exit_image_trans': 'http://x/trans2.jpg',
            'gantry_count': 1,
            'gantry_records': '[{"pic_id":1,"station_name":"G1"}]',
            'gantry_image_records': '[]',
        })

        resp = client.get('/api/audit/doris/vehicle/P1/full')
        assert resp.status_code == 200
        data = resp.json()
        assert data['passid'] == 'P1'
        assert data['gantry_records'] is not None
        assert data['gantry_image_records'] is not None
        assert 'audit_results' not in data
