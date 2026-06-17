"""任意车辆查询 API 集成测试 — 覆盖 /api/audit/trips 扩展参数 + /api/audit/trip/{passid}/full"""

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def client(temp_db, mock_ai_client, monkeypatch):
    monkeypatch.setenv('API_KEY', '')
    from apps.api.main import app
    app.state.truck_detector = None
    app.state.entry_exit_matcher = None
    app.state.aggregation_tasks = {}
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


def _seed_trip(repo, **overrides):
    base = {
        "passid": "V_TRIP",
        "entry_time": "2025-06-15 08:00:00",
        "exit_time": "2025-06-15 12:00:00",
        "entry_station_name": "入口A",
        "exit_station_name": "出口B",
        "entry_vehicle_id": "川A00001",
        "exit_vehicle_id": "川A00001",
        "entry_vehicle_type": 1,
        "exit_vehicle_type": 1,
        "entry_vehicle_color": 1,
        "exit_vehicle_color": 1,
        "entry_obu_id": "OBU0001",
        "audit_status": "PENDING",
        "risk_score": 0.0,
        "gantry_count": 0,
    }
    base.update(overrides)
    return repo.save_trip(base)


def _seed_audit_result(trip_id, fraud_type='TRUCK_USES_PASSENGER_OBU', is_suspicious=1,
                       risk_score=0.9, process_status='UNPROCESSED'):
    from apps.api.database.repositories.audit_repository import AuditRepository
    return AuditRepository().save_result({
        'audit_trip_id': trip_id,
        'fraud_type': fraud_type,
        'is_suspicious': is_suspicious,
        'risk_score': risk_score,
        'details': json.dumps({'test': True}),
        'process_status': process_status,
    })


@pytest.fixture
def repo():
    from apps.api.database.repositories.trip_repository import TripRepository
    return TripRepository()


class TestTripsListExtendedFilters:
    def test_filter_by_entry_vehicle_id(self, client, repo):
        _seed_trip(repo, passid='V1', entry_vehicle_id='川A11111')
        _seed_trip(repo, passid='V2', entry_vehicle_id='川B22222')

        resp = client.get('/api/audit/trips', params={'entry_vehicle_id': '川A11111'})
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 1
        assert data['trips'][0]['passid'] == 'V1'

    def test_vehicle_id_either_entry_or_exit(self, client, repo):
        _seed_trip(repo, passid='VE1', entry_vehicle_id='川X99999', exit_vehicle_id='川Y88888')
        _seed_trip(repo, passid='VE2', entry_vehicle_id='川Y88888', exit_vehicle_id='川X99999')

        resp = client.get('/api/audit/trips', params={'vehicle_id': '川X99999'})
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'VE1', 'VE2'}

    def test_vehicle_id_match_prefix(self, client, repo):
        _seed_trip(repo, passid='VP1', entry_vehicle_id='川AAA001')
        _seed_trip(repo, passid='VP2', entry_vehicle_id='川AAA002')
        _seed_trip(repo, passid='VP3', entry_vehicle_id='川BBB003')

        resp = client.get('/api/audit/trips', params={
            'entry_vehicle_id': '川AAA',
            'vehicle_id_match': 'prefix',
        })
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'VP1', 'VP2'}

    def test_risk_score_range(self, client, repo):
        _seed_trip(repo, passid='RR1', risk_score=0.3)
        _seed_trip(repo, passid='RR2', risk_score=0.7)
        _seed_trip(repo, passid='RR3', risk_score=0.95)

        resp = client.get('/api/audit/trips', params={
            'min_risk_score': 0.6,
            'max_risk_score': 0.9,
        })
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'RR2'}

    def test_gantry_count_range(self, client, repo):
        _seed_trip(repo, passid='GC1', gantry_count=0)
        _seed_trip(repo, passid='GC2', gantry_count=3)
        _seed_trip(repo, passid='GC3', gantry_count=5)

        resp = client.get('/api/audit/trips', params={'min_gantry_count': 2})
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'GC2', 'GC3'}

    def test_audit_status_filter(self, client, repo):
        _seed_trip(repo, passid='AS1', audit_status='PENDING')
        _seed_trip(repo, passid='AS2', audit_status='SUSPECTED')

        resp = client.get('/api/audit/trips', params={'audit_status': 'SUSPECTED'})
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'AS2'}

    def test_vehicle_type_filter(self, client, repo):
        _seed_trip(repo, passid='VT1', entry_vehicle_type=1, exit_vehicle_type=1)
        _seed_trip(repo, passid='VT2', entry_vehicle_type=2, exit_vehicle_type=2)

        resp = client.get('/api/audit/trips', params={'vehicle_type': 2})
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'VT2'}

    def test_obu_id_filter(self, client, repo):
        _seed_trip(repo, passid='OB1', entry_obu_id='OBU_SPECIAL')
        _seed_trip(repo, passid='OB2', entry_obu_id='OBU_OTHER')

        resp = client.get('/api/audit/trips', params={'entry_obu_id': 'OBU_SPECIAL'})
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'OB1'}

    def test_combined_filters(self, client, repo):
        _seed_trip(repo, passid='C1', entry_vehicle_id='川Z', risk_score=0.85, gantry_count=3)
        _seed_trip(repo, passid='C2', entry_vehicle_id='川Z', risk_score=0.5, gantry_count=0)
        _seed_trip(repo, passid='C3', entry_vehicle_id='川Y', risk_score=0.85, gantry_count=3)

        resp = client.get('/api/audit/trips', params={
            'vehicle_id': '川Z',
            'min_risk_score': 0.7,
            'min_gantry_count': 2,
        })
        assert resp.status_code == 200
        passids = {t['passid'] for t in resp.json()['trips']}
        assert passids == {'C1'}


class TestTripsListSortAndPagination:
    def test_order_by_risk_score_asc(self, client, repo):
        _seed_trip(repo, passid='S1', risk_score=0.9)
        _seed_trip(repo, passid='S2', risk_score=0.1)
        _seed_trip(repo, passid='S3', risk_score=0.5)

        resp = client.get('/api/audit/trips', params={
            'order_by': 'risk_score',
            'order': 'asc',
        })
        assert resp.status_code == 200
        assert [t['passid'] for t in resp.json()['trips']] == ['S2', 'S3', 'S1']

    def test_pagination(self, client, repo):
        for i in range(5):
            _seed_trip(repo, passid=f'P{i}')

        resp = client.get('/api/audit/trips', params={'limit': 2, 'offset': 0})
        assert resp.json()['total'] == 5
        assert len(resp.json()['trips']) == 2

    def test_invalid_order_by_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={'order_by': 'passid;DROP TABLE--'})
        assert resp.status_code == 400

    def test_invalid_vehicle_type_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={'vehicle_type': 99})
        assert resp.status_code == 400

    def test_invalid_risk_score_range_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={
            'min_risk_score': 0.9,
            'max_risk_score': 0.3,
        })
        assert resp.status_code == 400

    def test_invalid_vehicle_id_match_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={'vehicle_id_match': 'regex'})
        assert resp.status_code == 400

    def test_invalid_time_range_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={
            'start_time': '2025-06-20',
            'end_time': '2025-06-10',
        })
        assert resp.status_code == 400

    def test_invalid_order_returns_400(self, client):
        resp = client.get('/api/audit/trips', params={'order': 'sideways'})
        assert resp.status_code == 400


class TestTripFull:
    def test_404_for_missing_trip(self, client):
        resp = client.get('/api/audit/trip/NO_SUCH_TRIP/full')
        assert resp.status_code == 404

    def test_returns_gantry_image_records_null_when_myqsl_unreachable(self, client, repo):
        _seed_trip(repo, passid='FULL1',
                   entry_vehicle_id='川Q00001',
                   entry_time='2025-06-15 08:00:00',
                   exit_time='2025-06-15 12:00:00')
        # 默认 get_gantry_images_by_vehicle 在测试环境会失败（无外部 MySQL）
        # 端点应捕获异常并返回 gantry_image_records=null
        resp = client.get('/api/audit/trip/FULL1/full')
        assert resp.status_code == 200
        data = resp.json()
        assert data['passid'] == 'FULL1'
        assert 'gantry_image_records' in data
        assert data['gantry_image_records'] is None
        assert data['audit_results'] == []

    def test_returns_gantry_image_records_with_mock(self, client, repo):
        _seed_trip(repo, passid='FULL2',
                   entry_vehicle_id='川Q00002',
                   entry_time='2025-06-15 08:00:00',
                   exit_time='2025-06-15 12:00:00')
        fake_records = [
            {
                'GRANTRY_ID': 'G001', 'CAPTURETIME': '2025-06-15 09:00:00',
                'VEHICLEID': '川Q00002', 'VEHICLECOLOR': 1, 'ID': 'P001',
            }
        ]
        from apps.api.routers import audit as audit_router
        with patch.object(audit_router, 'get_gantry_images_by_vehicle', return_value=fake_records), \
             patch.object(audit_router, 'serialize_gantry_image_records', return_value='[{"x":1}]'):
            resp = client.get('/api/audit/trip/FULL2/full')
        assert resp.status_code == 200
        data = resp.json()
        assert data['gantry_image_records'] == '[{"x":1}]'

    def test_returns_audit_results(self, client, repo):
        trip_id = _seed_trip(repo, passid='FULL3')
        rid1 = _seed_audit_result(trip_id, 'TRUCK_USES_PASSENGER_OBU')
        rid2 = _seed_audit_result(trip_id, 'ENTRY_EXIT_MISMATCH')

        resp = client.get('/api/audit/trip/FULL3/full')
        assert resp.status_code == 200
        data = resp.json()
        assert data['passid'] == 'FULL3'
        assert len(data['audit_results']) == 2
        fraud_types = {r['fraud_type'] for r in data['audit_results']}
        assert fraud_types == {'TRUCK_USES_PASSENGER_OBU', 'ENTRY_EXIT_MISMATCH'}
        # JOIN 应把 trip 字段带进来
        for r in data['audit_results']:
            assert r['passid'] == 'FULL3'
            assert 'entry_time' in r
            assert 'entry_vehicle_id' in r
