"""客车 OBU 监测路由测试 — 覆盖 4 个新端点

端点:
  - GET  /api/audit/passenger-obu/overview         顶部 4 卡 + 30 天趋势
  - GET  /api/audit/passenger-obu/stats/daily     每日统计
  - GET  /api/audit/passenger-obu/anomalies       异常记录列表
  - POST /api/audit/detect/passenger-obu          单条触发检测
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(temp_db, mock_ai_client, monkeypatch):
    monkeypatch.setenv('API_KEY', '')
    from apps.api.main import app
    app.state.truck_detector = None
    app.state.entry_exit_matcher = None
    app.state.aggregation_tasks = {}
    with TestClient(app) as c:
        yield c


def _insert_trip_with_result(passid, fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
                             process_status='UNPROCESSED', source_side='ENTRY',
                             llm_verified=True, risk_score=0.85,
                             details_extra=None):
    """辅助:插入一条 trip + 一条 audit_result,返回 (trip_id, result_id)"""
    from apps.api.database.repositories.trip_repository import TripRepository
    from apps.api.database.repositories.audit_repository import AuditRepository

    trip_repo = TripRepository()
    trip_id = trip_repo.save_trip({
        'passid': passid,
        'entry_time': '2026-06-15 08:00:00',
        'exit_time': '2026-06-15 12:00:00',
        'entry_station_name': '站A',
        'exit_station_name': '站B',
        'entry_vehicle_id': '川A12345',
        'exit_vehicle_id': '川A12345',
        'entry_vehicle_type': 1,
        'exit_vehicle_type': 1,
        'entry_image_license': 'http://10.0.0.1/entry_license.jpg',
        'entry_image_trans': 'http://10.0.0.1/entry_trans.jpg',
        'exit_image_license': 'http://10.0.0.1/exit_license.jpg',
        'exit_image_trans': 'http://10.0.0.1/exit_trans.jpg',
        'entry_obu_id': 'OBU001',
        'exit_obu_id': 'OBU001',
    })
    details = {
        'source_side': source_side,
        'llm_verified': llm_verified,
        'llm_confidence': 0.93,
        'visual_vehicle_type': 'truck',
        'entry_image_trans': 'http://10.0.0.1/entry_trans.jpg',
        'exit_image_trans': 'http://10.0.0.1/exit_trans.jpg',
    }
    if details_extra:
        details.update(details_extra)
    result_id = AuditRepository().save_result({
        'audit_trip_id': trip_id,
        'fraud_type': fraud_type,
        'entry_vehicle_type': 1,
        'exit_vehicle_type': 1,
        'is_suspicious': 1,
        'risk_score': risk_score,
        'details': json.dumps(details),
        'process_status': process_status,
    })
    return trip_id, result_id


# ============================================================
# GET /passenger-obu/overview
# ============================================================


class TestPassengerObuOverviewRoute:
    def test_empty_returns_zeros(self, client):
        resp = client.get('/api/audit/passenger-obu/overview')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total_scanned'] == 0
        assert body['total_suspicious'] == 0
        assert body['total_pending'] == 0
        assert body['total_confirmed'] == 0
        assert body['last_run_at'] is None
        assert body['last_30_days'] == []

    def test_with_daily_stats_returns_aggregated(self, client):
        """灌入 daily stats,验证 overview 累计正确"""
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        stats_repo = TruckObuStatsRepository()
        stats_repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )

        resp = client.get('/api/audit/passenger-obu/overview')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total_scanned'] == 10
        assert body['total_suspicious'] == 3
        assert body['last_run_at'] == '2026-06-14 12:00:00'
        assert len(body['last_30_days']) >= 1
        assert any(d['date'] == '2026-06-14' for d in body['last_30_days'])

    def test_pending_count_includes_unprocessed(self, client):
        """灌入一条 UNPROCESSED 异常,total_pending 应 == 1"""
        _insert_trip_with_result(
            passid='P_OBV_1', process_status='UNPROCESSED',
        )
        resp = client.get('/api/audit/passenger-obu/overview')
        body = resp.json()
        assert body['total_pending'] == 1
        _insert_trip_with_result(
            passid='P_OBV_2', process_status='CONFIRMED',
        )
        resp2 = client.get('/api/audit/passenger-obu/overview')
        assert resp2.json()['total_pending'] == 1


# ============================================================
# GET /passenger-obu/stats/daily
# ============================================================


class TestPassengerObuDailyStatsRoute:
    def test_default_fraud_type_is_passenger(self, client):
        """不传 fraud_type → 默认只查 PASSENGER_USES_TRUCK_OBU_NON_NEW_A"""
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        repo = TruckObuStatsRepository()
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='TRUCK_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=99, suspicious_count_delta=0,
            last_run_at='2026-06-14 12:00:00',
        )

        resp = client.get('/api/audit/passenger-obu/stats/daily')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total'] == 1
        assert body['stats'][0]['fraud_type'] == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
        assert body['stats'][0]['scanned_count'] == 10

    def test_date_range_filter(self, client):
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        repo = TruckObuStatsRepository()
        for day in ('2026-06-12', '2026-06-13', '2026-06-14', '2026-06-15'):
            repo.upsert_daily_stat(
                date=day, fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
                scanned_count_delta=1, suspicious_count_delta=0,
                last_run_at=f'{day} 12:00:00',
            )

        resp = client.get(
            '/api/audit/passenger-obu/stats/daily'
            '?from_date=2026-06-13&to_date=2026-06-14'
        )
        body = resp.json()
        assert body['total'] == 2
        dates = [s['date'] for s in body['stats']]
        assert dates == ['2026-06-13', '2026-06-14']

    def test_explicit_fraud_type_query(self, client):
        """显式传 fraud_type → 可查其他 fraud_type"""
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        repo = TruckObuStatsRepository()
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='ENTRY_EXIT_MISMATCH',
            scanned_count_delta=99, suspicious_count_delta=0,
            last_run_at='2026-06-14 12:00:00',
        )

        resp = client.get(
            '/api/audit/passenger-obu/stats/daily?fraud_type=ENTRY_EXIT_MISMATCH'
        )
        body = resp.json()
        assert body['total'] == 1
        assert body['stats'][0]['fraud_type'] == 'ENTRY_EXIT_MISMATCH'


# ============================================================
# GET /passenger-obu/anomalies
# ============================================================


class TestPassengerObuAnomaliesRoute:
    def test_empty_returns_empty_list(self, client):
        resp = client.get('/api/audit/passenger-obu/anomalies')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total'] == 0
        assert body['anomalies'] == []
        assert body['limit'] == 50
        assert body['offset'] == 0

    def test_returns_passenger_obu_anomalies(self, client):
        _insert_trip_with_result(passid='P_ANOM_1', source_side='ENTRY')
        resp = client.get('/api/audit/passenger-obu/anomalies')
        body = resp.json()
        assert body['total'] == 1
        item = body['anomalies'][0]
        assert item['fraud_type'] == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
        assert item['source_side'] == 'ENTRY'
        assert item['llm_verified'] is True
        assert item['visual_vehicle_type'] == 'truck'
        assert item['entry_image_trans'] == 'http://10.0.0.1/entry_trans.jpg'
        assert item['process_status'] == 'UNPROCESSED'

    def test_filter_by_process_status(self, client):
        _insert_trip_with_result(passid='P_UNPROC', process_status='UNPROCESSED')
        _insert_trip_with_result(passid='P_CONFIRMED', process_status='CONFIRMED')

        resp = client.get('/api/audit/passenger-obu/anomalies?process_status=CONFIRMED')
        body = resp.json()
        assert body['total'] == 1
        assert body['anomalies'][0]['process_status'] == 'CONFIRMED'

    def test_pagination(self, client):
        for i in range(5):
            _insert_trip_with_result(passid=f'P_PAGE_{i}')

        resp = client.get('/api/audit/passenger-obu/anomalies?limit=2&offset=0')
        body = resp.json()
        assert body['total'] == 5
        assert len(body['anomalies']) == 2
        assert body['limit'] == 2

        resp2 = client.get('/api/audit/passenger-obu/anomalies?limit=2&offset=4')
        body2 = resp2.json()
        assert len(body2['anomalies']) == 1

    def test_corrupt_details_doesnt_break(self, client):
        """details 是非法 JSON → 字段降级为 None,不报错"""
        from apps.api.database.repositories.trip_repository import TripRepository
        from apps.api.database.repositories.audit_repository import AuditRepository

        trip_id = TripRepository().save_trip({
            'passid': 'P_BAD_DETAILS',
            'entry_time': '2026-06-15 08:00:00',
            'exit_time': '2026-06-15 12:00:00',
            'entry_vehicle_id': '川A1',
            'exit_vehicle_id': '川A1',
        })
        AuditRepository().save_result({
            'audit_trip_id': trip_id,
            'fraud_type': 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            'is_suspicious': 1,
            'risk_score': 0.85,
            'details': 'not-json-{[',
        })

        resp = client.get('/api/audit/passenger-obu/anomalies')
        body = resp.json()
        assert body['total'] == 1
        item = body['anomalies'][0]
        assert item['source_side'] is None
        assert item['visual_vehicle_type'] is None
        assert item['llm_verified'] is None


# ============================================================
# POST /detect/passenger-obu
# ============================================================


class TestDetectPassengerObuRoute:
    def test_trip_not_found_returns_404(self, client):
        resp = client.post(
            '/api/audit/detect/passenger-obu',
            json={'passid': 'NON_EXISTENT'},
        )
        assert resp.status_code == 404

    def test_no_hit_returns_not_suspicious(self, client):
        """trip 存在但 detect_trip 返回 None → 200 + is_suspicious=False"""
        from apps.api.database.repositories.trip_repository import TripRepository
        TripRepository().save_trip({
            'passid': 'P_NO_HIT',
            'entry_time': '2026-06-15 08:00:00',
            'exit_time': '2026-06-15 12:00:00',
            'entry_vehicle_id': '川A1',
            'exit_vehicle_id': '川A1',
        })
        with patch(
            'apps.api.services.passenger_obu_detector.detect_trip',
            return_value=None,
        ):
            resp = client.post(
                '/api/audit/detect/passenger-obu',
                json={'passid': 'P_NO_HIT'},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body['is_suspicious'] is False
            assert body['fraud_type'] == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
            assert body['details'] is None

    def test_hit_returns_suspicious_with_details(self, client):
        """命中 → 返回完整 details 并落库"""
        from apps.api.database.repositories.trip_repository import TripRepository
        TripRepository().save_trip({
            'passid': 'P_HIT_DETECT',
            'entry_time': '2026-06-15 08:00:00',
            'exit_time': '2026-06-15 12:00:00',
            'entry_vehicle_id': '川A1',
            'exit_vehicle_id': '川A1',
        })
        hit_details = {
            'source_side': 'BOTH',
            'entry_vehicle_type': 1,
            'exit_vehicle_type': 1,
            'entry_obu_id': 'OBU1',
            'exit_obu_id': 'OBU2',
            'entry_media_type': 1,
            'exit_media_type': 1,
            'entry_visual_type': 'truck',
            'exit_visual_type': 'truck',
            'visual_vehicle_type': 'truck',
            'llm_verified': True,
            'llm_confidence': 0.95,
            'risk_score': 0.95,
        }
        with patch(
            'apps.api.services.passenger_obu_detector.detect_trip',
            return_value=hit_details,
        ):
            resp = client.post(
                '/api/audit/detect/passenger-obu',
                json={'passid': 'P_HIT_DETECT'},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body['is_suspicious'] is True
            assert body['fraud_type'] == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
            assert body['details']['source_side'] == 'BOTH'
            assert body['details']['llm_verified'] is True

            from apps.api.database.repositories.audit_repository import AuditRepository
            suspects = AuditRepository().get_suspects(
                fraud_types=['PASSENGER_USES_TRUCK_OBU_NON_NEW_A'],
            )
            assert len(suspects) == 1
            details = json.loads(suspects[0]['details'])
            assert details['source_side'] == 'BOTH'
            assert details['rule_version'] == 'v1'

    def test_missing_passid_returns_422(self, client):
        resp = client.post('/api/audit/detect/passenger-obu', json={})
        assert resp.status_code == 422
