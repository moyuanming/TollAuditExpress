"""_execute_truck_obu_audit 单元测试 — 货车 OBU 监测任务执行器

行为契约:
  - 首次执行 (last_run_at=None) → 窗口 [start_time, NOW]
  - 增量执行 (last_run_at=X)    → 窗口 [X - 5min, NOW]
  - 候选 > page_size 时分页拉取,scanned 累加
  - 命中 trip 后写入 audit_results,score 固定 0.85,details 含 source_side
  - 写完审计后调用 stats_repo.upsert_daily_stat
  - 返回 dict 含 window_start / window_end / scanned / suspicious / anomaly_count
  - _normalize_truck_obu_rules 默认值正确
  - _parse_dt 支持多种字符串格式
"""

import json
from datetime import datetime
from contextlib import contextmanager
import sqlite3

import pytest

from apps.api.services.task_executor import (
    _execute_truck_obu_audit,
    _normalize_truck_obu_rules,
    _parse_dt,
)
from apps.api.database.repositories.trip_repository import TripRepository
from apps.api.services.truck_obu_metadata_detector import FRAUD_TYPE


# ============================================================
# helpers
# ============================================================


@contextmanager
def temp_db_conn(path):
    """绕过 conftest 的 wrapper,直接拿 sqlite3.Connection 写测试数据。"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _insert_trip(conn, **fields):
    """直接往 audit_trips 写一条样本;只设置与监测相关的字段。"""
    base = {
        'passid': fields.get('passid', 'P001'),
        'entry_time': '2026-06-14 10:00:00',
        'entry_station_name': 'A站',
        'exit_time': '2026-06-14 12:00:00',
        'exit_station_name': 'B站',
        'entry_vehicle_id': None,
        'entry_vehicle_type': None,
        'entry_media_type': None,
        'entry_obu_id': None,
        'exit_vehicle_id': None,
        'exit_vehicle_type': None,
        'exit_media_type': None,
        'exit_obu_id': None,
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
# 纯函数测试（不依赖 DB）
# ============================================================


class TestNormalizeRules:
    def test_default_values(self):
        rules = _normalize_truck_obu_rules({})
        assert rules['start_time'] == '2026-06-01 00:00:00'
        assert rules['vehicle_types'] == [14, 15, 16]
        assert rules['media_type'] == 1
        assert rules['plate_prefix_exclude'] == '新A'
        assert rules['limit'] == 2000
        assert rules['page_size'] == 500

    def test_overrides(self):
        rules = _normalize_truck_obu_rules({
            'start_time': '2026-01-01 00:00:00',
            'vehicle_types': [14],
            'media_type': 2,
            'plate_prefix_exclude': '京B',
            'limit': 100,
            'page_size': 50,
        })
        assert rules['start_time'] == '2026-01-01 00:00:00'
        assert rules['vehicle_types'] == [14]
        assert rules['media_type'] == 2
        assert rules['plate_prefix_exclude'] == '京B'
        assert rules['limit'] == 100
        assert rules['page_size'] == 50

    def test_overrides_string_ints(self):
        """filter_rules 通常来自 JSON,数字字段可能是 str — 应当正确转 int"""
        rules = _normalize_truck_obu_rules({
            'media_type': '1',
            'limit': '500',
            'page_size': '100',
        })
        assert rules['media_type'] == 1
        assert isinstance(rules['media_type'], int)
        assert rules['limit'] == 500
        assert rules['page_size'] == 100


class TestParseDt:
    def test_datetime_passthrough(self):
        dt = datetime(2026, 6, 14, 10, 0, 0)
        assert _parse_dt(dt) is dt

    def test_space_format(self):
        assert _parse_dt('2026-06-14 10:00:00') == datetime(2026, 6, 14, 10, 0, 0)

    def test_iso_format(self):
        assert _parse_dt('2026-06-14T10:00:00') == datetime(2026, 6, 14, 10, 0, 0)

    def test_date_only(self):
        assert _parse_dt('2026-06-14') == datetime(2026, 6, 14)

    def test_invalid_returns_now(self):
        """不可解析时安全回落,不让任务挂掉"""
        result = _parse_dt('not-a-date')
        assert isinstance(result, datetime)

    def test_empty_returns_now(self):
        result = _parse_dt('')
        assert isinstance(result, datetime)


# ============================================================
# 执行器集成测试（用 temp_db）
# ============================================================


class TestFirstRunWindow:
    """last_run_at=None → 窗口从 filter_rules.start_time 起"""

    def test_first_run_uses_start_time(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            _insert_trip(
                conn,
                passid='OBU-FIRST-1',
                entry_time='2026-06-14 10:00:00',
                entry_vehicle_id='甘A11111', entry_vehicle_type=14, entry_media_type=1,
                entry_obu_id='OBU-E-001',
                exit_vehicle_id='甘A11111', exit_vehicle_type=14, exit_media_type=1,
                exit_obu_id='OBU-X-001',
            )

        result = _execute_truck_obu_audit(
            filter_rules={},
            task={},
            trip_repo=TripRepository(),
        )

        assert result['window_start'] == '2026-06-01 00:00:00'
        assert result['task_type'] == 'truck_obu_audit'
        assert result['scanned'] >= 1
        assert result['suspicious'] >= 1


class TestIncrementalRunWindow:
    """last_run_at='2026-06-14 10:00:00' → 窗口起点前移 5 分钟"""

    def test_incremental_run_window_overlap(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            _insert_trip(
                conn,
                passid='OBU-INCR-1',
                entry_time='2026-06-14 09:57:00',
                entry_vehicle_id='甘A22222', entry_vehicle_type=15, entry_media_type=1,
                entry_obu_id='OBU-E-002',
                exit_vehicle_id='甘A22222', exit_vehicle_type=15, exit_media_type=1,
                exit_obu_id='OBU-X-002',
            )

        result = _execute_truck_obu_audit(
            filter_rules={},
            task={'last_run_at': '2026-06-14 10:00:00'},
            trip_repo=TripRepository(),
        )

        # 起点 = 2026-06-14 10:00:00 - 5min = 2026-06-14 09:55:00
        assert result['window_start'] == '2026-06-14 09:55:00'


class TestPagination:
    """候选 > page_size 时分页拉,scanned 累加"""

    def test_pagination_aggregates_scanned(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            for i in range(7):
                _insert_trip(
                    conn,
                    passid=f'OBU-PAGE-{i}',
                    entry_time=f'2026-06-14 10:0{i % 10}:00',
                    entry_vehicle_id=f'甘A1000{i}', entry_vehicle_type=14, entry_media_type=1,
                    entry_obu_id=f'OBU-E-{i}',
                    exit_vehicle_id=f'甘A1000{i}', exit_vehicle_type=14, exit_media_type=1,
                    exit_obu_id=f'OBU-X-{i}',
                )

        result = _execute_truck_obu_audit(
            filter_rules={'page_size': 3, 'limit': 100},
            task={},
            trip_repo=TripRepository(),
        )

        assert result['scanned'] == 7
        assert result['suspicious'] == 7


class TestHitPersistsToAuditResults:
    """命中 trip 后写入 audit_results,details 含 source_side"""

    def test_hit_writes_audit_result_with_correct_fields(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            trip_id = _insert_trip(
                conn,
                passid='OBU-HIT-1',
                entry_time='2026-06-14 11:00:00',
                entry_vehicle_id='甘B11111', entry_vehicle_type=14, entry_media_type=1,
                entry_obu_id='OBU-E-HIT',
                exit_vehicle_id='甘B11111', exit_vehicle_type=14, exit_media_type=1,
                exit_obu_id='OBU-X-HIT',
            )

        result = _execute_truck_obu_audit(
            filter_rules={},
            task={},
            trip_repo=TripRepository(),
        )

        assert result['suspicious'] == 1
        anomaly_id = result['anomaly_ids_sample'][0]

        with temp_db_conn(temp_db) as conn:
            row = dict(conn.execute(
                "SELECT * FROM audit_results WHERE id = ?", (anomaly_id,)
            ).fetchone())
        assert row['audit_trip_id'] == trip_id
        assert row['fraud_type'] == FRAUD_TYPE
        assert row['is_suspicious'] == 1
        assert row['risk_score'] == 0.85
        assert row['process_status'] == 'UNPROCESSED'

        details = json.loads(row['details'])
        assert details['source_side'] == 'BOTH'
        assert details['entry_obu_id'] == 'OBU-E-HIT'
        assert details['exit_obu_id'] == 'OBU-X-HIT'
        assert details['entry_media_type'] == 1
        assert details['exit_media_type'] == 1


class TestNonCandidateNotScanned:
    """不符合候选过滤的 trip 应被 SQL 层过滤掉,scanned 不计数"""

    def test_passenger_or_mtc_or_null_id_not_scanned(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            # 客车(不满足 type IN (14,15,16))
            _insert_trip(
                conn,
                passid='OBU-NONCAND-1',
                entry_time='2026-06-14 12:00:00',
                entry_vehicle_id='京A12345', entry_vehicle_type=1, entry_media_type=1,
                exit_vehicle_id='京A12345', exit_vehicle_type=1, exit_media_type=1,
            )
            # MTC(不满足 media=1)
            _insert_trip(
                conn,
                passid='OBU-NONCAND-2',
                entry_time='2026-06-14 12:01:00',
                entry_vehicle_id='甘A99999', entry_vehicle_type=14, entry_media_type=2,
                exit_vehicle_id='甘A99999', exit_vehicle_type=14, exit_media_type=2,
            )
            # vehicle_id 为 None (SQL 排除)
            _insert_trip(
                conn,
                passid='OBU-NONCAND-3',
                entry_time='2026-06-14 12:02:00',
                entry_vehicle_id=None, entry_vehicle_type=14, entry_media_type=1,
                exit_vehicle_id=None, exit_vehicle_type=14, exit_media_type=1,
            )
            # 新A 开头 (SQL 排除 — NOT LIKE '新A%')
            _insert_trip(
                conn,
                passid='OBU-NONCAND-4',
                entry_time='2026-06-14 12:03:00',
                entry_vehicle_id='新A88888', entry_vehicle_type=14, entry_media_type=1,
                exit_vehicle_id='新A88888', exit_vehicle_type=14, exit_media_type=1,
            )

        result = _execute_truck_obu_audit(
            filter_rules={},
            task={},
            trip_repo=TripRepository(),
        )

        # 全部不满足候选过滤 → scanned=0
        assert result['scanned'] == 0
        assert result['suspicious'] == 0
        assert result['anomaly_count'] == 0

        with temp_db_conn(temp_db) as conn:
            rows = conn.execute("SELECT COUNT(*) c FROM audit_results").fetchone()
        assert dict(rows)['c'] == 0


class TestDailyStatsUpserted:
    """写完审计后,audit_truck_obu_daily_stats 应累加"""

    def test_daily_stats_accumulated(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            _insert_trip(
                conn,
                passid='OBU-STAT-1',
                entry_time='2026-06-14 13:00:00',
                entry_vehicle_id='甘C11111', entry_vehicle_type=14, entry_media_type=1,
                entry_obu_id='OBU-E-S1',
                exit_vehicle_id='甘C11111', exit_vehicle_type=14, exit_media_type=1,
                exit_obu_id='OBU-X-S1',
            )

        _execute_truck_obu_audit(
            filter_rules={},
            task={},
            trip_repo=TripRepository(),
        )

        with temp_db_conn(temp_db) as conn:
            row = dict(conn.execute(
                "SELECT * FROM audit_truck_obu_daily_stats WHERE date = '2026-06-01'"
            ).fetchone())
        assert row['fraud_type'] == FRAUD_TYPE
        assert row['scanned_count'] == 1
        assert row['suspicious_count'] == 1
        assert row['last_run_at'] is not None

    def test_daily_stats_incremental_upsert(self, temp_db):
        """第二次执行:同样的 (date, fraud_type) 应累加,不是覆盖"""
        with temp_db_conn(temp_db) as conn:
            _insert_trip(
                conn,
                passid='OBU-STAT-2',
                entry_time='2026-06-14 14:00:00',
                entry_vehicle_id='甘D11111', entry_vehicle_type=14, entry_media_type=1,
                entry_obu_id='OBU-E-S2',
                exit_vehicle_id='甘D11111', exit_vehicle_type=14, exit_media_type=1,
                exit_obu_id='OBU-X-S2',
            )

        # 两次执行都用同一窗口 (last_run_at=13:30 → start=13:25,14:00 的 trip 都在内)
        task = {'last_run_at': '2026-06-14 13:30:00'}
        _execute_truck_obu_audit(
            filter_rules={},
            task=task,
            trip_repo=TripRepository(),
        )
        _execute_truck_obu_audit(
            filter_rules={},
            task=task,
            trip_repo=TripRepository(),
        )

        with temp_db_conn(temp_db) as conn:
            row = dict(conn.execute(
                "SELECT * FROM audit_truck_obu_daily_stats WHERE date = '2026-06-14'"
            ).fetchone())
        # 累加:1+1=2
        assert row['scanned_count'] == 2
        assert row['suspicious_count'] == 2


class TestReturnStructure:
    """返回 dict 应含所有约定的键"""

    def test_return_dict_has_all_keys(self, temp_db):
        with temp_db_conn(temp_db) as conn:
            _insert_trip(
                conn,
                passid='OBU-RET-1',
                entry_time='2026-06-14 15:00:00',
                entry_vehicle_id='甘E11111', entry_vehicle_type=14, entry_media_type=1,
                entry_obu_id='OBU-E-R1',
                exit_vehicle_id='甘E11111', exit_vehicle_type=14, exit_media_type=1,
                exit_obu_id='OBU-X-R1',
            )

        result = _execute_truck_obu_audit(
            filter_rules={},
            task={},
            trip_repo=TripRepository(),
        )

        for key in (
            'task_type', 'window_start', 'window_end',
            'scanned', 'suspicious', 'anomaly_count', 'anomaly_ids_sample',
        ):
            assert key in result, f"missing key: {key}"
        assert result['task_type'] == 'truck_obu_audit'
        assert isinstance(result['scanned'], int)
        assert isinstance(result['suspicious'], int)
        assert isinstance(result['anomaly_ids_sample'], list)
        assert result['anomaly_count'] == len(result['anomaly_ids_sample'])

    def test_empty_window_returns_zero(self, temp_db):
        """窗口内无候选 → scanned=0, suspicious=0, anomaly_count=0"""
        result = _execute_truck_obu_audit(
            filter_rules={'start_time': '2099-01-01 00:00:00'},
            task={},
            trip_repo=TripRepository(),
        )

        assert result['scanned'] == 0
        assert result['suspicious'] == 0
        assert result['anomaly_count'] == 0
        assert result['anomaly_ids_sample'] == []
