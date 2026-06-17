"""run_ai_verify_batch_for_suspects 单元测试 — mock vehicle-ai-service compare + 真实 SQLite 仓储。

audit_results 表的 llm_* 字段 (llm_is_same_vehicle / llm_confidence / llm_reason / llm_model /
llm_checked_at) 沿用旧名,留待后续 schema 迁移统一改 ai_verify_*。
"""
import os
import sys
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _seed_pending_suspect(audit_repo, *, passid='P1', fraud_type='TRUCK_USES_PASSENGER_OBU',
                          visual='truck'):
    """通过 audit_trips + audit_results 插入一条"待 AI 复核"的可疑记录。"""
    from apps.api.database.connection import get_connection

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_trips (passid, entry_time, exit_time,
                                     entry_station_name, exit_station_name,
                                     entry_visual_type, exit_visual_type,
                                     entry_image_license, exit_image_license)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (passid, '2026-06-01T08:00:00', '2026-06-01T10:00:00',
              '入口A', '出口B', visual, visual,
              'http://x/entry.jpg', 'http://x/exit.jpg'))
        trip_id = cur.lastrowid
        cur.execute("""
            INSERT INTO audit_results (audit_trip_id, fraud_type,
                                       entry_visual_type, exit_visual_type,
                                       is_suspicious, risk_score,
                                       process_status)
            VALUES (?, ?, ?, ?, 1, 0.9, 'UNPROCESSED')
        """, (trip_id, fraud_type, visual, visual))
        sid = cur.lastrowid
        conn.commit()
    return sid


class TestRunAiVerifyBatchForSuspects:
    def test_empty_db_returns_zero(self, temp_db):
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects
        result = run_ai_verify_batch_for_suspects(limit=50, max_workers=2)
        assert result == {'processed': 0, 'succeeded': 0, 'skipped': 0, 'errors': []}

    def test_pending_suspect_with_visual_types_is_processed(self, temp_db):
        from apps.api.database.repositories.audit_repository import AuditRepository
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        audit_repo = AuditRepository()
        sid = _seed_pending_suspect(audit_repo, passid='P_OK')

        with patch(
            'apps.api.services.ai_verify_batch.compare_vehicles_by_passid',
            return_value={
                'passid': 'P_OK',
                'is_same_vehicle': True,
                'confidence': 0.92,
                'reason': '车牌号一致',
                'entry_image_url': 'http://x/entry.jpg',
                'exit_image_url': 'http://x/exit.jpg',
                'model': 'qwen2.5-vl-72b',
                'elapsed_ms': 1234,
            },
        ):
            result = run_ai_verify_batch_for_suspects(limit=50, max_workers=2)

        assert result['processed'] == 1
        assert result['succeeded'] == 1
        assert result['skipped'] == 0

        row = audit_repo.get_suspect_by_id(sid)
        assert row['llm_is_same_vehicle'] == 1
        assert abs(row['llm_confidence'] - 0.92) < 1e-6
        assert row['llm_reason'] == '车牌号一致'
        assert row['llm_model'] == 'qwen2.5-vl-72b'
        assert row['llm_checked_at'] is not None
        datetime.fromisoformat(row['llm_checked_at'].replace('Z', '+00:00'))

    def test_different_vehicle_verdict_written(self, temp_db):
        from apps.api.database.repositories.audit_repository import AuditRepository
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        audit_repo = AuditRepository()
        sid = _seed_pending_suspect(audit_repo, passid='P_DIFF')

        with patch(
            'apps.api.services.ai_verify_batch.compare_vehicles_by_passid',
            return_value={
                'is_same_vehicle': False,
                'confidence': 0.88,
                'reason': '车牌不同',
                'model': 'qwen2.5-vl-72b',
            },
        ):
            result = run_ai_verify_batch_for_suspects(limit=50, max_workers=2)

        assert result['succeeded'] == 1
        row = audit_repo.get_suspect_by_id(sid)
        assert row['llm_is_same_vehicle'] == 0
        assert abs(row['llm_confidence'] - 0.88) < 1e-6

    def test_comparator_error_skips_suspect_no_verdict_written(self, temp_db):
        from apps.api.database.repositories.audit_repository import AuditRepository
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        audit_repo = AuditRepository()
        sid = _seed_pending_suspect(audit_repo, passid='P_ERR')

        with patch(
            'apps.api.services.ai_verify_batch.compare_vehicles_by_passid',
            return_value={'error': 'image_url_missing', 'field': 'entry_image_license'},
        ):
            result = run_ai_verify_batch_for_suspects(limit=50, max_workers=2)

        assert result['processed'] == 1
        assert result['succeeded'] == 0
        assert result['skipped'] == 1
        assert len(result['errors']) == 1
        assert 'image_url_missing' in result['errors'][0]

        row = audit_repo.get_suspect_by_id(sid)
        # 失败时不写入,下次 batch 可重试
        assert row['llm_checked_at'] is None
        assert row['llm_is_same_vehicle'] is None

    def test_visual_type_missing_excluded_by_repo_filter(self, temp_db):
        from apps.api.database.connection import get_connection
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        # 缺 visual_type 的可疑记录
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO audit_trips (passid, entry_visual_type, exit_visual_type,
                                         entry_image_license, exit_image_license)
                VALUES (?, NULL, NULL, 'http://x/entry.jpg', 'http://x/exit.jpg')
            """, ('P_NOVIS',))
            trip_id = cur.lastrowid
            cur.execute("""
                INSERT INTO audit_results (audit_trip_id, fraud_type,
                                           entry_visual_type, exit_visual_type,
                                           is_suspicious, risk_score, process_status)
                VALUES (?, 'TRUCK_USES_PASSENGER_OBU', NULL, NULL, 1, 0.9, 'UNPROCESSED')
            """, (trip_id,))
            conn.commit()

        with patch('apps.api.services.ai_verify_batch.compare_vehicles_by_passid') as mock_cmp:
            result = run_ai_verify_batch_for_suspects(limit=50, max_workers=2)
            mock_cmp.assert_not_called()

        assert result['processed'] == 0
        assert result['succeeded'] == 0

    def test_processes_multiple_suspects_concurrently(self, temp_db):
        from apps.api.database.repositories.audit_repository import AuditRepository
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        audit_repo = AuditRepository()
        ids = [
            _seed_pending_suspect(audit_repo, passid=f'P_{i}')
            for i in range(5)
        ]

        with patch(
            'apps.api.services.ai_verify_batch.compare_vehicles_by_passid',
            return_value={
                'is_same_vehicle': True,
                'confidence': 0.8,
                'reason': 'ok',
                'model': 'qwen2.5-vl-72b',
            },
        ) as mock_cmp:
            result = run_ai_verify_batch_for_suspects(limit=50, max_workers=4)

        assert result['processed'] == 5
        assert result['succeeded'] == 5
        assert mock_cmp.call_count == 5
        called_passids = {call.args[0] for call in mock_cmp.call_args_list}
        assert called_passids == {f'P_{i}' for i in range(5)}
        for sid in ids:
            row = audit_repo.get_suspect_by_id(sid)
            assert row['llm_checked_at'] is not None

    def test_limit_caps_processing(self, temp_db):
        from apps.api.database.repositories.audit_repository import AuditRepository
        from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects

        audit_repo = AuditRepository()
        for i in range(10):
            _seed_pending_suspect(audit_repo, passid=f'P_L{i}')

        with patch(
            'apps.api.services.ai_verify_batch.compare_vehicles_by_passid',
            return_value={
                'is_same_vehicle': True, 'confidence': 0.9,
                'reason': 'ok', 'model': 'qwen2.5-vl-72b',
            },
        ):
            result = run_ai_verify_batch_for_suspects(limit=3, max_workers=2)

        assert result['processed'] == 3
        assert result['succeeded'] == 3
