"""task_executor 单元测试 — 任务执行器

行为契约:
  - set_log_context / clear_log_context / get_log_lines: 日志缓冲管理
  - _CaptureHandler: 日志捕获到执行缓冲
  - execute_task: 根据任务类型分发执行
  - _execute_aggregate_detect: 聚合+检测
  - _execute_detect_only: 仅检测
  - _execute_re_detect: 补检测
  - _execute_multi_detect: 多维度检测
  - _execute_passenger_obu_audit: 客车OBU审计
  - _execute_llm_verify: AI二次复核
  - _normalize_passenger_obu_rules: 规则标准化
  - _parse_dt: 时间解析
"""

import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

from apps.api.services.task_executor import (
    _CaptureHandler,
    _execute_aggregate_detect,
    _execute_detect_only,
    _execute_llm_verify,
    _execute_multi_detect,
    _execute_re_detect,
    _normalize_passenger_obu_rules,
    _parse_dt,
    clear_log_context,
    execute_task,
    get_log_lines,
    set_log_context,
)

# ============================================================
# Log context management
# ============================================================


class TestLogContext:
    def test_set_log_context_initializes_buffer(self):
        set_log_context(1)
        assert get_log_lines(1) == []

    def test_clear_log_context_removes_buffer(self):
        set_log_context(2)
        clear_log_context(2)
        assert get_log_lines(2) == []

    def test_get_log_lines_returns_empty_for_unknown_id(self):
        assert get_log_lines(999) == []

    def test_capture_handler_appends_to_buffer(self):
        set_log_context(3)
        handler = _CaptureHandler(level=logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert get_log_lines(3) == ["hello"]
        clear_log_context(3)

    def test_capture_handler_ignores_when_no_context(self):
        handler = _CaptureHandler(level=logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="no ctx",
            args=(),
            exc_info=None,
        )
        # Should not crash
        handler.emit(record)

    def test_capture_handler_ignores_when_buffer_removed(self):
        set_log_context(4)
        handler = _CaptureHandler(level=logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Remove buffer before emit
        clear_log_context(4)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="orphan",
            args=(),
            exc_info=None,
        )
        handler.emit(record)  # Should not crash


# ============================================================
# _parse_dt
# ============================================================


class TestParseDt:
    def test_parses_standard_datetime_string(self):
        result = _parse_dt("2026-06-14 10:30:00")
        assert result == datetime(2026, 6, 14, 10, 30, 0)

    def test_parses_iso_datetime_string(self):
        result = _parse_dt("2026-06-14T10:30:00")
        assert result == datetime(2026, 6, 14, 10, 30, 0)

    def test_parses_date_only_string(self):
        result = _parse_dt("2026-06-14")
        assert result == datetime(2026, 6, 14)

    def test_returns_datetime_as_is(self):
        dt = datetime(2026, 6, 14, 10, 0, 0)
        assert _parse_dt(dt) is dt

    def test_returns_now_for_none(self):
        result = _parse_dt(None)
        assert isinstance(result, datetime)

    def test_returns_now_for_empty_string(self):
        result = _parse_dt("")
        assert isinstance(result, datetime)

    def test_returns_now_for_invalid_format(self):
        result = _parse_dt("not-a-date")
        assert isinstance(result, datetime)


# ============================================================
# _normalize_passenger_obu_rules
# ============================================================


class TestNormalizePassengerObuRules:
    def test_returns_defaults_for_empty_dict(self):
        rules = _normalize_passenger_obu_rules({})
        assert rules["start_time"] == "2026-06-01 00:00:00"
        assert rules["declared_vehicle_type"] == 1
        assert rules["plate_prefix_exclude"] == "新A"
        assert rules["limit"] == 2000
        assert rules["page_size"] == 500
        assert rules["max_workers"] == 4

    def test_overrides_custom_values(self):
        rules = _normalize_passenger_obu_rules(
            {
                "start_time": "2026-01-01 00:00:00",
                "declared_vehicle_type": "2",
                "plate_prefix_exclude": "京B",
                "limit": "1000",
                "page_size": "100",
                "max_workers": "8",
            }
        )
        assert rules["start_time"] == "2026-01-01 00:00:00"
        assert rules["declared_vehicle_type"] == 2
        assert rules["plate_prefix_exclude"] == "京B"
        assert rules["limit"] == 1000
        assert rules["page_size"] == 100
        assert rules["max_workers"] == 8


# ============================================================
# execute_task
# ============================================================


class TestExecuteTask:
    @patch("apps.api.services.task_executor._execute_aggregate_detect", return_value={"aggregated": 5})
    def test_aggregate_detect_task_type(self, mock_exec):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "aggregate_detect"})
        assert result == {"aggregated": 5}

    @patch("apps.api.services.task_executor._execute_detect_only", return_value={"detected": 3})
    def test_detect_only_task_type(self, mock_exec):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "detect_only"})
        assert result == {"detected": 3}

    @patch("apps.api.services.task_executor._execute_multi_detect", return_value={"multi_detect": True})
    def test_multi_detect_task_type(self, mock_exec):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "multi_detect"})
        assert result == {"multi_detect": True}

    @patch("apps.api.services.task_executor._execute_re_detect", return_value={"detected": 2})
    def test_re_detect_task_type(self, mock_exec):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "re_detect"})
        assert result == {"detected": 2}

    @patch("apps.api.services.task_executor._execute_passenger_obu_audit", return_value={"scanned": 100})
    def test_passenger_obu_audit_task_type(self, mock_exec):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "passenger_obu_audit"})
        assert result == {"scanned": 100}

    @patch("apps.api.services.task_executor._execute_llm_verify", return_value={"verified": 10})
    def test_llm_verify_task_type(self, mock_exec):
        result = execute_task({"task_type": "llm_verify"})
        assert result == {"verified": 10}

    def test_unknown_task_type_returns_error(self):
        mock_repo = MagicMock()
        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            result = execute_task({"task_type": "unknown_type"})
        assert "error" in result
        assert "unknown_type" in result["error"]

    def test_default_task_type_is_aggregate_detect(self):
        mock_repo = MagicMock()
        with (
            patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo),
            patch("apps.api.services.task_executor._execute_aggregate_detect", return_value={"ok": True}) as mock_exec,
        ):
            execute_task({})
        mock_exec.assert_called_once()

    def test_filter_rules_parsed_from_json(self):
        mock_repo = MagicMock()
        with (
            patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo),
            patch("apps.api.services.task_executor._execute_aggregate_detect", return_value={"ok": True}) as mock_exec,
        ):
            execute_task({"task_type": "aggregate_detect", "filter_rules": '{"days": 5}'})
        # filter_rules should be parsed to dict
        call_args = mock_exec.call_args[0]
        assert call_args[0] == {"days": 5}

    def test_invalid_filter_rules_treated_as_empty(self):
        mock_repo = MagicMock()
        with (
            patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo),
            patch("apps.api.services.task_executor._execute_aggregate_detect", return_value={"ok": True}) as mock_exec,
        ):
            execute_task({"task_type": "aggregate_detect", "filter_rules": "not-json"})
        call_args = mock_exec.call_args[0]
        assert call_args[0] == {}


# ============================================================
# _execute_aggregate_detect
# ============================================================


class TestExecuteAggregateDetect:
    @patch("apps.api.services.trip_aggregator.TripAggregator")
    def test_calls_aggregate_recent_trips(self, mock_agg_class):
        mock_agg = MagicMock()
        mock_agg.aggregate_recent_trips.return_value = 10
        mock_agg_class.return_value = mock_agg

        mock_repo = MagicMock()
        mock_repo.get_stats.return_value = {"suspected_trips": 3}

        result = _execute_aggregate_detect({}, mock_repo)
        assert result["aggregated"] == 10
        assert result["suspected"] == 3

    @patch("apps.api.services.trip_aggregator.TripAggregator")
    def test_uses_filter_rules_days_and_limit(self, mock_agg_class):
        mock_agg = MagicMock()
        mock_agg.aggregate_recent_trips.return_value = 5
        mock_agg_class.return_value = mock_agg

        mock_repo = MagicMock()
        mock_repo.get_stats.return_value = {"suspected_trips": 0}

        _execute_aggregate_detect({"days": 3, "limit": 100}, mock_repo)
        mock_agg.aggregate_recent_trips.assert_called_once_with(days=3, limit=100, run_detection=True)


# ============================================================
# _execute_detect_only
# ============================================================


class TestExecuteDetectOnly:
    def test_detects_trips_without_visual(self):
        mock_repo = MagicMock()
        mock_repo.get_trips_without_visual.return_value = []

        with patch("apps.api.services.entry_exit_matcher.EntryExitMatcher"):
            result = _execute_detect_only({}, mock_repo)
        assert result == {"aggregated": 0, "detected": 0, "suspected": 0}

    def test_filters_by_exit_station(self):
        mock_repo = MagicMock()
        mock_repo.get_trips_without_visual.return_value = [
            {
                "id": 1,
                "passid": "P1",
                "exit_station_name": "站A",
                "entry_station_name": "站B",
                "entry_image_license": "http://x/e.jpg",
                "exit_image_license": "http://x/x.jpg",
            },
            {
                "id": 2,
                "passid": "P2",
                "exit_station_name": "站C",
                "entry_station_name": "站B",
                "entry_image_license": "http://x/e.jpg",
                "exit_image_license": "http://x/x.jpg",
            },
        ]

        mock_matcher = MagicMock()
        mock_matcher.compare.return_value = {"_comparison_success": True, "is_suspicious": True, "fingerprint_sim": 0.3}

        with patch("apps.api.services.entry_exit_matcher.EntryExitMatcher", return_value=mock_matcher):
            result = _execute_detect_only({"exit_station": "站A"}, mock_repo)

        # Only trip 1 matches exit_station filter
        assert result["detected"] == 1


# ============================================================
# _execute_re_detect
# ============================================================


class TestExecuteReDetect:
    def test_re_detects_trips_without_visual(self):
        mock_repo = MagicMock()
        mock_repo.get_trips_without_visual.return_value = []

        with patch("apps.api.services.entry_exit_matcher.EntryExitMatcher"):
            result = _execute_re_detect(mock_repo)
        assert result == {"aggregated": 0, "detected": 0, "suspected": 0}

    def test_skips_trips_without_images(self):
        mock_repo = MagicMock()
        mock_repo.get_trips_without_visual.return_value = [
            {"id": 1, "passid": "P1", "entry_image_license": None, "exit_image_license": None},
        ]

        with patch("apps.api.services.entry_exit_matcher.EntryExitMatcher"):
            result = _execute_re_detect(mock_repo)
        assert result["detected"] == 0


# ============================================================
# _execute_multi_detect
# ============================================================


class TestExecuteMultiDetect:
    def test_runs_rule_engine_and_detectors(self):
        mock_repo = MagicMock()
        mock_repo.get_trips.return_value = []

        with (
            patch("apps.api.services.rule_engine.RuleEngine"),
            patch("apps.api.services.rule_loader.load_rules", return_value=[]),
            patch("apps.api.services.detectors.all_detectors", return_value=[]),
        ):
            result = _execute_multi_detect({}, mock_repo)
        assert result == {"multi_detect": True, "detected": 0, "suspected": 0}

    def test_handles_double_encoded_filter_rules(self):
        mock_repo = MagicMock()
        mock_repo.get_trips.return_value = []

        with (
            patch("apps.api.services.rule_engine.RuleEngine"),
            patch("apps.api.services.rule_loader.load_rules", return_value=[]),
            patch("apps.api.services.detectors.all_detectors", return_value=[]),
        ):
            # Pass filter_rules as a JSON string (double encoded)
            result = _execute_multi_detect('{"limit": 50}', mock_repo)
        assert result["multi_detect"] is True

    def test_invalid_filter_rules_treated_as_empty(self):
        mock_repo = MagicMock()
        mock_repo.get_trips.return_value = []

        with (
            patch("apps.api.services.rule_engine.RuleEngine"),
            patch("apps.api.services.rule_loader.load_rules", return_value=[]),
            patch("apps.api.services.detectors.all_detectors", return_value=[]),
        ):
            result = _execute_multi_detect("not-json", mock_repo)
        assert result["multi_detect"] is True


# ============================================================
# _execute_llm_verify
# ============================================================


class TestExecuteLlmVerify:
    def test_calls_ai_verify_batch_with_defaults(self):
        with patch(
            "apps.api.services.ai_verify_batch.run_ai_verify_batch_for_suspects", return_value={"ok": True}
        ) as mock_run:
            result = _execute_llm_verify({})
        mock_run.assert_called_once_with(limit=50, max_workers=4)
        assert result == {"ok": True}

    def test_passes_custom_limit_and_workers(self):
        with patch(
            "apps.api.services.ai_verify_batch.run_ai_verify_batch_for_suspects", return_value={"ok": True}
        ) as mock_run:
            _execute_llm_verify({"limit": 100, "max_workers": 8})
        mock_run.assert_called_once_with(limit=100, max_workers=8)
