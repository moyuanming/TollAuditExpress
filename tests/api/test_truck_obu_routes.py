"""货车 OBU 监测 API 集成测试

覆盖端点:
  - GET /api/audit/truck-obu/overview
  - GET /api/audit/truck-obu/stats/daily
  - GET /api/audit/truck-obu/anomalies
"""

import json
from contextlib import contextmanager
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db, mock_ai_client, monkeypatch):
    monkeypatch.setenv('API_KEY', '')
    from apps.api.main import app
    with TestClient(app) as c:
        yield c


@contextmanager
def raw_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _seed_trip(conn, **fields):
    """直接写一条 audit_trips 样本"""
    base = {
        'passid': fields.get('passid', 'P001'),
        'entry_time': '2026-06-14 10:00:00',
        'entry_station_name': 'A站',
        'exit_time': '2026-06-14 12:00:00',
        'exit_station_name': 'B站',
        'entry_vehicle_id': None, 'entry_vehicle_type': None,
        'entry_media_type': None, 'entry_obu_id': None,
        'exit_vehicle_id': None, 'exit_vehicle_type': None,
        'exit_media_type': None, 'exit_obu_id': None,
        'audit_status': 'PENDING',
    }
    base.update(fields)
    cur = conn.execute(
        """
        INSERT INTO audit_trips (
            passid, entry_time, entry_station_name, exit_time, exit_station_name,
            entry_vehicle_id, entry_vehicle_type, entry_media_type, entry_obu_id,
            exit_vehicle_id, exit_vehicle_type, exit_media_type, exit_obu_id,
            audit_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            base['passid'], base['entry_time'], base['entry_station_name'],
            base['exit_time'], base['exit_station_name'],
            base['entry_vehicle_id'], base['entry_vehicle_type'], base['entry_media_type'], base['entry_obu_id'],
            base['exit_vehicle_id'], base['exit_vehicle_type'], base['exit_media_type'], base['exit_obu_id'],
            base['audit_status'],
        ),
    )
    conn.commit()
    return cur.lastrowid


# ============================================================
# /truck-obu/overview
# ============================================================


class TestTruckObuOverview:
    def test_overview_empty(self, client):
        resp = client.get('/api/audit/truck-obu/overview')
        assert resp.status_code == 200
        data = resp.json()
        # 4 个 stat 字段
        for key in ('total_scanned', 'total_suspicious', 'total_pending', 'total_confirmed'):
            assert key in data, f"missing key: {key}"
        assert data['total_scanned'] == 0
        assert data['total_suspicious'] == 0
        assert data['total_pending'] == 0
        assert data['total_confirmed'] == 0
        assert data['last_run_at'] is None
        assert 'last_30_days' in data
        assert data['last_30_days'] == []

    def test_overview_aggregates_stats(self, client, temp_db):
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        repo = TruckObuStatsRepository()
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='TRUCK_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=100, suspicious_count_delta=8,
            last_run_at='2026-06-14 12:00:00',
        )

        resp = client.get('/api/audit/truck-obu/overview')
        assert resp.status_code == 200
        data = resp.json()
        assert data['total_scanned'] == 100
        assert data['total_suspicious'] == 8
        assert data['last_run_at'] == '2026-06-14 12:00:00'

    def test_overview_includes_pending_count(self, client, temp_db):
        """total_pending 应来自 audit_results 里的 UNPROCESSED 数"""
        with raw_db(temp_db) as conn:
            trip_id = _seed_trip(conn, passid='OBU-PEND-1', entry_time='2026-06-14 10:00:00',
                                 entry_vehicle_id='甘A11111', entry_vehicle_type=14, entry_media_type=1,
                                 entry_obu_id='OBU-E-P1',
                                 exit_vehicle_id='甘A11111', exit_vehicle_type=14, exit_media_type=1,
                                 exit_obu_id='OBU-X-P1')
            conn.execute(
                """INSERT INTO audit_results
                   (audit_trip_id, fraud_type, is_suspicious, risk_score, process_status, details)
                   VALUES (?,?,?,?,?,?)""",
                (trip_id, 'TRUCK_USES_TRUCK_OBU_NON_NEW_A', 1, 0.85, 'UNPROCESSED', '{}'),
            )
            conn.commit()

        resp = client.get('/api/audit/truck-obu/overview')
        data = resp.json()
        assert data['total_pending'] == 1


# ============================================================
# /truck-obu/stats/daily
# ============================================================


class TestTruckObuDailyStats:
    def test_daily_stats_empty(self, client):
        resp = client.get('/api/audit/truck-obu/stats/daily')
        assert resp.status_code == 200
        data = resp.json()
        assert data['stats'] == []
        assert data['total'] == 0

    def test_daily_stats_with_filter(self, client, temp_db):
        from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
        repo = TruckObuStatsRepository()
        for day in ('2026-06-12', '2026-06-13', '2026-06-14'):
            repo.upsert_daily_stat(
                date=day, fraud_type='TRUCK_USES_TRUCK_OBU_NON_NEW_A',
                scanned_count_delta=10, suspicious_count_delta=1,
                last_run_at=f'{day} 12:00:00',
            )

        resp = client.get(
            '/api/audit/truck-obu/stats/daily'
            '?from_date=2026-06-13&to_date=2026-06-14'
            '&fraud_type=TRUCK_USES_TRUCK_OBU_NON_NEW_A'
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 2
        assert [s['date'] for s in data['stats']] == ['2026-06-13', '2026-06-14']


# ============================================================
# /truck-obu/anomalies
# ============================================================


class TestTruckObuAnomalies:
    def test_anomalies_empty(self, client):
        resp = client.get('/api/audit/truck-obu/anomalies')
        assert resp.status_code == 200
        data = resp.json()
        assert data['anomalies'] == []
        assert data['total'] == 0
        assert data['limit'] == 50
        assert data['offset'] == 0

    def test_anomalies_filter_by_process_status(self, client, temp_db):
        """仅返回 process_status 匹配的"""
        with raw_db(temp_db) as conn:
            trip_id = _seed_trip(conn, passid='OBU-ANOM-1', entry_time='2026-06-14 10:00:00',
                                 entry_vehicle_id='甘A11111', entry_vehicle_type=14, entry_media_type=1,
                                 entry_obu_id='OBU-E-A1',
                                 exit_vehicle_id='甘A11111', exit_vehicle_type=14, exit_media_type=1,
                                 exit_obu_id='OBU-X-A1')
            for status in ('UNPROCESSED', 'CONFIRMED'):
                conn.execute(
                    """INSERT INTO audit_results
                       (audit_trip_id, fraud_type, is_suspicious, risk_score, process_status, details)
                       VALUES (?,?,?,?,?,?)""",
                    (trip_id, 'TRUCK_USES_TRUCK_OBU_NON_NEW_A', 1, 0.85, status,
                     json.dumps({'source_side': 'BOTH', 'entry_obu_id': 'OBU-E-A1',
                                 'exit_obu_id': 'OBU-X-A1', 'entry_media_type': 1,
                                 'exit_media_type': 1})),
                )
            conn.commit()

        resp_all = client.get('/api/audit/truck-obu/anomalies')
        assert resp_all.json()['total'] == 2

        resp_un = client.get('/api/audit/truck-obu/anomalies?process_status=UNPROCESSED')
        data = resp_un.json()
        assert data['total'] == 1
        assert data['anomalies'][0]['process_status'] == 'UNPROCESSED'
        assert data['anomalies'][0]['source_side'] == 'BOTH'

    def test_anomalies_extract_obu_id_and_media_type_from_details(self, client, temp_db):
        """obu_id / media_type 应从 details JSON 里解析出来(JOIN 字段不全)"""
        with raw_db(temp_db) as conn:
            trip_id = _seed_trip(conn, passid='OBU-ANOM-2', entry_time='2026-06-14 11:00:00',
                                 entry_vehicle_id='甘A22222', entry_vehicle_type=14, entry_media_type=1,
                                 entry_obu_id='OBU-E-DETAIL',
                                 exit_vehicle_id='甘A22222', exit_vehicle_type=14, exit_media_type=1,
                                 exit_obu_id='OBU-X-DETAIL')
            conn.execute(
                """INSERT INTO audit_results
                   (audit_trip_id, fraud_type, is_suspicious, risk_score, process_status, details)
                   VALUES (?,?,?,?,?,?)""",
                (trip_id, 'TRUCK_USES_TRUCK_OBU_NON_NEW_A', 1, 0.85, 'UNPROCESSED',
                 json.dumps({'source_side': 'ENTRY', 'entry_obu_id': 'OBU-E-DETAIL',
                             'exit_obu_id': 'OBU-X-DETAIL', 'entry_media_type': 1,
                             'exit_media_type': 1, 'rule_version': 'v1'})),
            )
            conn.commit()

        resp = client.get('/api/audit/truck-obu/anomalies')
        item = resp.json()['anomalies'][0]
        assert item['entry_obu_id'] == 'OBU-E-DETAIL'
        assert item['exit_obu_id'] == 'OBU-X-DETAIL'
        assert item['entry_media_type'] == 1
        assert item['exit_media_type'] == 1
        assert item['source_side'] == 'ENTRY'

    def test_anomalies_pagination(self, client, temp_db):
        with raw_db(temp_db) as conn:
            for i in range(5):
                trip_id = _seed_trip(conn, passid=f'OBU-PAGE-{i}', entry_time=f'2026-06-14 1{i}:00:00',
                                     entry_vehicle_id=f'甘A{i}0000', entry_vehicle_type=14, entry_media_type=1,
                                     entry_obu_id=f'OBU-E-{i}',
                                     exit_vehicle_id=f'甘A{i}0000', exit_vehicle_type=14, exit_media_type=1,
                                     exit_obu_id=f'OBU-X-{i}')
                conn.execute(
                    """INSERT INTO audit_results
                       (audit_trip_id, fraud_type, is_suspicious, risk_score, process_status, details)
                       VALUES (?,?,?,?,?,?)""",
                    (trip_id, 'TRUCK_USES_TRUCK_OBU_NON_NEW_A', 1, 0.85, 'UNPROCESSED',
                     json.dumps({'source_side': 'BOTH', 'entry_obu_id': f'OBU-E-{i}',
                                 'exit_obu_id': f'OBU-X-{i}', 'entry_media_type': 1,
                                 'exit_media_type': 1})),
                )
            conn.commit()

        resp1 = client.get('/api/audit/truck-obu/anomalies?limit=2&offset=0')
        data1 = resp1.json()
        assert len(data1['anomalies']) == 2
        assert data1['total'] == 5
        assert data1['limit'] == 2
        assert data1['offset'] == 0

        resp2 = client.get('/api/audit/truck-obu/anomalies?limit=2&offset=2')
        data2 = resp2.json()
        assert len(data2['anomalies']) == 2
        ids1 = {a['id'] for a in data1['anomalies']}
        ids2 = {a['id'] for a in data2['anomalies']}
        assert ids1.isdisjoint(ids2)


# ============================================================
# 端到端：创建任务 + 执行 + 数据落地
# ============================================================


class TestEndToEndExecution:
    """验证:创建定时任务 → 立即执行 → audit_results 多 1 条 → 每日 stats 累加"""

    def test_create_task_then_execute_writes_data(self, client, temp_db):
        # 1. 准备一条候选 trip
        with raw_db(temp_db) as conn:
            _seed_trip(conn, passid='OBU-E2E-1', entry_time='2026-06-14 10:00:00',
                       entry_vehicle_id='甘A11111', entry_vehicle_type=14, entry_media_type=1,
                       entry_obu_id='OBU-E-E2E',
                       exit_vehicle_id='甘A11111', exit_vehicle_type=14, exit_media_type=1,
                       exit_obu_id='OBU-X-E2E')

        # 2. 创建定时任务
        create_resp = client.post('/api/tasks', json={
            'name': '货车 OBU 监测测试',
            'description': 'e2e',
            'task_type': 'truck_obu_audit',
            'filter_rules': {
                'start_time': '2026-06-01 00:00:00',
                'vehicle_types': [14, 15, 16],
                'media_type': 1,
                'plate_prefix_exclude': '新A',
                'limit': 100,
                'page_size': 50,
            },
            'schedule_type': 'interval',
            'schedule_config': {'minutes': 30},
        })
        assert create_resp.status_code == 201
        task = create_resp.json()
        task_id = task['id']
        assert task['task_type'] == 'truck_obu_audit'

        # 3. 同步直接调用执行器(避免后台线程异步导致测试 flaky)
        from apps.api.services.task_executor import _execute_truck_obu_audit
        from apps.api.database.repositories.trip_repository import TripRepository
        rules = task['filter_rules']
        if isinstance(rules, str):
            rules = json.loads(rules)
        result = _execute_truck_obu_audit(
            filter_rules=rules,
            task=task,
            trip_repo=TripRepository(),
        )

        # 4. 验证返回 dict
        assert result['scanned'] == 1
        assert result['suspicious'] == 1
        assert 'window_start' in result
        assert 'window_end' in result
        assert result['window_start'] == '2026-06-01 00:00:00'

        # 5. 验证 audit_results 落地
        with raw_db(temp_db) as conn:
            count = dict(conn.execute("SELECT COUNT(*) c FROM audit_results").fetchone())
            sample = dict(conn.execute(
                "SELECT * FROM audit_results WHERE fraud_type='TRUCK_USES_TRUCK_OBU_NON_NEW_A'"
            ).fetchone())
        assert count['c'] == 1
        assert sample['is_suspicious'] == 1
        assert sample['risk_score'] == 0.85

        # 6. 验证每日 stats 累加
        overview = client.get('/api/audit/truck-obu/overview').json()
        assert overview['total_scanned'] == 1
        assert overview['total_suspicious'] == 1

        # 7. 验证 anomalies 接口能查到这条
        anomalies = client.get('/api/audit/truck-obu/anomalies').json()
        assert anomalies['total'] == 1
        assert anomalies['anomalies'][0]['source_side'] == 'BOTH'
