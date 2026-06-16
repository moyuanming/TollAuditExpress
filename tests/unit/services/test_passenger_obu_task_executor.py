"""_execute_passenger_obu_audit 任务执行器测试

行为契约:
  - 首次执行(last_run_at 为空)→ 窗口 = [start_time, NOW]
  - 增量执行(last_run_at 存在)→ 窗口 = [last_run_at - 5min, NOW]
  - 命中/未命中路径都写 daily stat
  - 公共服务异常/超时 → 该条跳过,不中断整批
  - anomaly_ids_sample 最多 50 个
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository
from apps.api.services.passenger_obu_detector import FRAUD_TYPE
from apps.api.services.task_executor import _execute_passenger_obu_audit

# ============================================================
# Fixtures
# ============================================================


def _make_trip(
    trip_id=1,
    passid="PASS_TEST_1",
    entry_vt=1,
    exit_vt=1,
    entry_vid="川A12345",
    exit_vid="川A12345",
    entry_img="http://example.com/entry_trans.jpg",
    exit_img="http://example.com/exit_trans.jpg",
    entry_time="2026-06-14 10:00:00",
    exit_time="2026-06-14 12:00:00",
):
    return {
        "id": trip_id,
        "passid": passid,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_vehicle_id": entry_vid,
        "exit_vehicle_id": exit_vid,
        "entry_vehicle_type": entry_vt,
        "exit_vehicle_type": exit_vt,
        "entry_media_type": 1,
        "exit_media_type": 1,
        "entry_obu_id": "OBU001",
        "exit_obu_id": "OBU001",
        "entry_image_trans": entry_img,
        "exit_image_trans": exit_img,
        "entry_visual_type": None,
        "exit_visual_type": None,
    }


def _hit_details(side="ENTRY"):
    return {
        "fraud_type": FRAUD_TYPE,
        "source_side": side,
        "entry_vehicle_type": 1,
        "exit_vehicle_type": 1,
        "entry_obu_id": "OBU001",
        "exit_obu_id": "OBU001",
        "entry_image_trans": "http://example.com/entry_trans.jpg",
        "exit_image_trans": "http://example.com/exit_trans.jpg",
        "entry_visual_type": None,
        "exit_visual_type": None,
        "llm_verified": True,
        "llm_confidence": 0.93,
        "visual_vehicle_type": "truck",
        "risk_score": 0.85,
    }


def _seed_trip(trip_id, passid):
    """在 audit_trips 落一条真实记录(供 get_suspects JOIN 校验)。"""
    from apps.api.database.repositories.trip_repository import TripRepository

    TripRepository().save_trip(
        {
            "passid": passid,
            "entry_time": "2026-06-14 10:00:00",
            "exit_time": "2026-06-14 12:00:00",
            "entry_vehicle_id": "川A12345",
            "exit_vehicle_id": "川A12345",
        }
    )


@pytest.fixture
def trip_repo():
    return MagicMock()


# ============================================================
# 时间窗
# ============================================================


class TestTimeWindow:
    @patch("apps.api.services.doris_trip_query.find_passenger_obu_candidates_doris", return_value=[])
    @patch("apps.api.database.repositories.truck_obu_stats_repository.TruckObuStatsRepository")
    @patch("apps.api.database.repositories.audit_repository.AuditRepository")
    def test_first_run_window_uses_start_time(
        self, mock_audit_repo_cls, mock_stats_repo_cls, mock_find_candidates, temp_db, trip_repo, mock_ai_client
    ):
        """首次执行(last_run_at=None)→ 窗口起点 = rules.start_time"""
        task = {"last_run_at": None}
        result = _execute_passenger_obu_audit(
            {"start_time": "2026-06-01 00:00:00"},
            task,
            trip_repo,
        )
        assert result is not None
        assert result["task_type"] == "passenger_obu_audit"
        assert result["window_start"] == "2026-06-01 00:00:00"

    @patch("apps.api.services.doris_trip_query.find_passenger_obu_candidates_doris", return_value=[])
    @patch("apps.api.database.repositories.truck_obu_stats_repository.TruckObuStatsRepository")
    @patch("apps.api.database.repositories.audit_repository.AuditRepository")
    def test_incremental_run_subtracts_5_minutes(
        self, mock_audit_repo_cls, mock_stats_repo_cls, mock_find_candidates, temp_db, trip_repo, mock_ai_client
    ):
        """增量执行 → 窗口起点 = last_run_at - 5min"""
        trip_repo.find_passenger_obu_candidates.return_value = []
        task = {"last_run_at": "2026-06-14 12:30:00"}
        result = _execute_passenger_obu_audit({}, task, trip_repo)

        call_kwargs = trip_repo.find_passenger_obu_candidates.call_args.kwargs
        # 12:30 - 5min = 12:25
        assert call_kwargs["start_time"] == "2026-06-14 12:25:00"
        assert result["window_start"] == "2026-06-14 12:25:00"

    def test_incremental_run_with_full_iso_format(self, temp_db, trip_repo, mock_ai_client):
        """支持 ISO T 分隔符格式的 last_run_at"""
        trip_repo.find_passenger_obu_candidates.return_value = []
        task = {"last_run_at": "2026-06-14T12:30:00"}
        _execute_passenger_obu_audit({}, task, trip_repo)
        call_kwargs = trip_repo.find_passenger_obu_candidates.call_args.kwargs
        assert call_kwargs["start_time"] == "2026-06-14 12:25:00"

    def test_default_start_time(self, temp_db, trip_repo, mock_ai_client):
        """filter_rules 完全为空 → 走默认 '2026-06-01 00:00:00'"""
        trip_repo.find_passenger_obu_candidates.return_value = []
        task = {"last_run_at": None}
        _execute_passenger_obu_audit({}, task, trip_repo)
        call_kwargs = trip_repo.find_passenger_obu_candidates.call_args.kwargs
        assert call_kwargs["start_time"] == "2026-06-01 00:00:00"


# ============================================================
# 候选分页
# ============================================================


class TestCandidatePagination:
    def test_pagination_breaks_on_empty(self, temp_db, trip_repo, mock_ai_client):
        trip_repo.find_passenger_obu_candidates.return_value = []
        task = {"last_run_at": None}
        result = _execute_passenger_obu_audit({}, task, trip_repo)
        assert trip_repo.find_passenger_obu_candidates.call_count == 1
        assert result["scanned"] == 0
        assert result["suspicious"] == 0

    def test_single_page(self, temp_db, trip_repo, mock_ai_client):
        """单页未满(< page_size)→ 一次调用就退出"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=i, passid=f"P{i}") for i in range(1, 4)
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)
            assert trip_repo.find_passenger_obu_candidates.call_count == 1
            assert result["scanned"] == 3
            assert result["suspicious"] == 0

    def test_multi_page_looping(self, temp_db, trip_repo, mock_ai_client):
        """第一页满 → 继续翻页;第二页未满 → 退出"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.side_effect = [
                [_make_trip(trip_id=i, passid=f"P{i}") for i in range(500)],
                [],
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)
            assert trip_repo.find_passenger_obu_candidates.call_count == 2
            assert trip_repo.find_passenger_obu_candidates.call_args_list[1].kwargs["offset"] == 500
            assert result["scanned"] == 500

    def test_limit_caps_total_scanned(self, temp_db, trip_repo, mock_ai_client):
        """即使不断翻页,scanned 累计达到 rules['limit'] 后也停止"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=i, passid=f"P{i}") for i in range(500)
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({"limit": 1200}, task, trip_repo)
            assert result["scanned"] == 1500  # 3 页 × 500


# ============================================================
# 命中路径
# ============================================================


class TestHitPath:
    def test_hit_writes_audit_result_and_daily_stat(self, temp_db, trip_repo, mock_ai_client):
        """命中 → 写 audit_results + 累加 daily stat"""
        # 先 seed 一条 trip,取得其真实 id,然后让 mock 候选人引用这个 id
        from apps.api.database.repositories.trip_repository import TripRepository

        seeded_id = TripRepository().save_trip(
            {
                "passid": "PASS_HIT_1",
                "entry_time": "2026-06-14 10:00:00",
                "exit_time": "2026-06-14 12:00:00",
                "entry_vehicle_id": "川A12345",
                "exit_vehicle_id": "川A12345",
            }
        )
        with patch(
            "apps.api.services.passenger_obu_detector.detect_trip",
            return_value=_hit_details("ENTRY"),
        ):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=seeded_id, passid="PASS_HIT_1"),
            ]
            task = {"last_run_at": "2026-06-14 10:00:00"}
            result = _execute_passenger_obu_audit({}, task, trip_repo)

            assert result["scanned"] == 1
            assert result["suspicious"] == 1
            assert result["anomaly_count"] == 1
            assert len(result["anomaly_ids_sample"]) == 1

            # 直接读 audit_results(不走 JOIN,避免 trip 关联问题)
            from apps.api.database.doris_connection import get_connection

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT fraud_type, details, process_status FROM audit_results")
                rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["fraud_type"] == FRAUD_TYPE
            details = json.loads(rows[0]["details"])
            assert details["source_side"] == "ENTRY"
            assert details["llm_verified"] is True
            assert details["visual_vehicle_type"] == "truck"
            assert details["rule_version"] == "v1"

            stats_repo = TruckObuStatsRepository()
            stats = stats_repo.get_daily_stats(fraud_type=FRAUD_TYPE)
            assert len(stats) == 1
            assert stats[0]["date"] == "2026-06-14"
            assert stats[0]["scanned_count"] == 1
            assert stats[0]["suspicious_count"] == 1

    def test_per_day_attribution(self, temp_db, trip_repo, mock_ai_client):
        """跨天扫描的候选,scanned/suspicious 应按 entry_time 所在日分别累加,
        而非全部归到 start_dt 当天(修复前的 bug 是 day = start_dt.strftime(...))。
        """
        from apps.api.database.repositories.trip_repository import TripRepository

        repo = TripRepository()
        id_d1 = repo.save_trip(
            {
                "passid": "P_D1",
                "entry_time": "2026-06-13 23:30:00",
                "exit_time": "2026-06-14 00:30:00",
                "entry_vehicle_id": "川A12345",
                "exit_vehicle_id": "川A12345",
            }
        )
        id_d2 = repo.save_trip(
            {
                "passid": "P_D2",
                "entry_time": "2026-06-14 00:10:00",
                "exit_time": "2026-06-14 01:00:00",
                "entry_vehicle_id": "川A12345",
                "exit_vehicle_id": "川A12345",
            }
        )
        with patch(
            "apps.api.services.passenger_obu_detector.detect_trip",
            return_value=_hit_details("ENTRY"),
        ):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(
                    trip_id=id_d1,
                    passid="P_D1",
                    entry_vt=1,
                    exit_vt=1,
                    entry_img="http://example.com/entry_d1.jpg",
                    exit_img="http://example.com/exit_d1.jpg",
                    entry_time="2026-06-13 23:30:00",
                    exit_time="2026-06-14 00:30:00",
                ),
                _make_trip(
                    trip_id=id_d2,
                    passid="P_D2",
                    entry_vt=1,
                    exit_vt=1,
                    entry_img="http://example.com/entry_d2.jpg",
                    exit_img="http://example.com/exit_d2.jpg",
                    entry_time="2026-06-14 00:10:00",
                    exit_time="2026-06-14 01:00:00",
                ),
            ]
            # 增量任务,last_run_at=6/13 23:55 → start_dt=6/13 23:50
            task = {"last_run_at": "2026-06-13 23:55:00"}
            _execute_passenger_obu_audit({}, task, trip_repo)

        stats_repo = TruckObuStatsRepository()
        stats = stats_repo.get_daily_stats(fraud_type=FRAUD_TYPE)
        by_date = {s["date"]: s for s in stats}
        # P_D1 的 entry_time 在 6/13,P_D2 的 entry_time 在 6/14 — 各归各的日
        assert by_date["2026-06-13"]["scanned_count"] == 1
        assert by_date["2026-06-13"]["suspicious_count"] == 1
        assert by_date["2026-06-14"]["scanned_count"] == 1
        assert by_date["2026-06-14"]["suspicious_count"] == 1

    def test_miss_path_still_writes_daily_stat(self, temp_db, trip_repo, mock_ai_client):
        """未命中 → daily stat 仍累加 scanned,但 suspicious=0"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=20, passid="PASS_MISS_1"),
                _make_trip(trip_id=21, passid="PASS_MISS_2"),
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)

            assert result["scanned"] == 2
            assert result["suspicious"] == 0
            assert result["anomaly_count"] == 0
            assert result["anomaly_ids_sample"] == []

            stats_repo = TruckObuStatsRepository()
            stats = stats_repo.get_daily_stats(fraud_type=FRAUD_TYPE)
            assert len(stats) == 1
            assert stats[0]["scanned_count"] == 2
            assert stats[0]["suspicious_count"] == 0

    def test_anomaly_ids_sample_capped_at_50(self, temp_db, trip_repo, mock_ai_client):
        """命中数 > 50 时,anomaly_ids_sample 截断到 50"""
        from apps.api.database.repositories.trip_repository import TripRepository

        repo = TripRepository()
        seeded_ids = []
        # seed 60 条 trip,记录每条真实 id
        for i in range(1, 61):
            tid = repo.save_trip(
                {
                    "passid": f"P{i}",
                    "entry_time": "2026-06-14 10:00:00",
                    "exit_time": "2026-06-14 12:00:00",
                    "entry_vehicle_id": "川A12345",
                    "exit_vehicle_id": "川A12345",
                }
            )
            seeded_ids.append(tid)
        with patch(
            "apps.api.services.passenger_obu_detector.detect_trip",
            return_value=_hit_details("ENTRY"),
        ):
            trips = [_make_trip(trip_id=seeded_ids[i], passid=f"P{i + 1}") for i in range(60)]
            trip_repo.find_passenger_obu_candidates.return_value = trips
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)

            assert result["suspicious"] == 60
            assert result["anomaly_count"] == 60
            assert len(result["anomaly_ids_sample"]) == 50


# ============================================================
# 异常分支
# ============================================================


class TestExceptionHandling:
    def test_save_result_failure_skips_trip(self, temp_db, trip_repo, mock_ai_client):
        """save_result 抛异常 → 该条记 warning,继续跑后续 trip"""
        for i in range(1, 4):
            _seed_trip(trip_id=i, passid=f"P_{i}")
        with (
            patch(
                "apps.api.services.passenger_obu_detector.detect_trip",
                return_value=_hit_details("ENTRY"),
            ),
            patch(
                "apps.api.database.repositories.audit_repository.AuditRepository.save_result",
                side_effect=[RuntimeError("db down"), 100, 101],
            ),
        ):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=1, passid="P_FAIL"),
                _make_trip(trip_id=2, passid="P_OK_1"),
                _make_trip(trip_id=3, passid="P_OK_2"),
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)

            assert result["scanned"] == 3
            assert result["suspicious"] == 2
            assert result["anomaly_count"] == 2


# ============================================================
# 入参透传
# ============================================================


class TestRulesPassthrough:
    def test_custom_plate_prefix_exclude(self, temp_db, trip_repo, mock_ai_client):
        """自定义 plate_prefix_exclude(非'新A')应透传"""
        trip_repo.find_passenger_obu_candidates.return_value = []
        task = {"last_run_at": None}
        _execute_passenger_obu_audit({"plate_prefix_exclude": "京B"}, task, trip_repo)
        call_kwargs = trip_repo.find_passenger_obu_candidates.call_args.kwargs
        assert call_kwargs["plate_prefix_exclude"] == "京B"

    def test_custom_page_size(self, temp_db, trip_repo, mock_ai_client):
        """自定义 page_size 应影响分页粒度"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.side_effect = [
                [_make_trip(trip_id=i, passid=f"P{i}") for i in range(50)],
                [],
            ]
            task = {"last_run_at": None}
            _execute_passenger_obu_audit({"page_size": 50}, task, trip_repo)
            first_kwargs = trip_repo.find_passenger_obu_candidates.call_args_list[0].kwargs
            assert first_kwargs["limit"] == 50
            assert first_kwargs["offset"] == 0

    def test_default_max_workers_is_four(self, temp_db, trip_repo, mock_ai_client):
        """未指定 max_workers 时默认 4(并行化 AI service 调用的 worker 数)"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=1, passid="P1"),
            ]
            with patch("apps.api.services.task_executor.ThreadPoolExecutor") as ex_mock:
                task = {"last_run_at": None}
                _execute_passenger_obu_audit({}, task, trip_repo)
                ex_mock.assert_called_once_with(max_workers=4)

    def test_custom_max_workers_passthrough(self, temp_db, trip_repo, mock_ai_client):
        """自定义 max_workers 透传到 ThreadPoolExecutor"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip", return_value=None):
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=1, passid="P1"),
            ]
            with patch("apps.api.services.task_executor.ThreadPoolExecutor") as ex_mock:
                task = {"last_run_at": None}
                _execute_passenger_obu_audit({"max_workers": 8}, task, trip_repo)
                ex_mock.assert_called_once_with(max_workers=8)

    def test_detect_trip_exception_isolated(self, temp_db, trip_repo, mock_ai_client):
        """detect_trip 抛异常时,只丢该条 trip,其他正常处理(R1 路径不应因单条崩溃整批)"""
        with patch("apps.api.services.passenger_obu_detector.detect_trip") as det:
            det.side_effect = [RuntimeError("boom"), None, None]
            trip_repo.find_passenger_obu_candidates.return_value = [
                _make_trip(trip_id=i, passid=f"P{i}") for i in range(1, 4)
            ]
            task = {"last_run_at": None}
            result = _execute_passenger_obu_audit({}, task, trip_repo)
            assert result["scanned"] == 3
            assert result["suspicious"] == 0  # 异常 trip 不算命中
            # 其它 trip 的 daily stat 仍正常累加
            stats_repo = TruckObuStatsRepository()
            stats = stats_repo.get_daily_stats(fraud_type=FRAUD_TYPE)
            assert sum(s["scanned_count"] for s in stats) == 3
