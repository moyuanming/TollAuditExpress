"""task_scheduler 单元测试 — 后台任务调度器

行为契约:
  - start_scheduler: 仅启动一次 daemon 线程
  - _check_and_execute_due_tasks: 检查到期任务并执行
  - _has_running_execution: 检查任务是否有活跃执行
  - _cleanup_stuck_executions: 清理超时执行记录
  - _schedule_next_run: 计算下次执行时间
  - execute_task_manually: 手动执行任务
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from apps.api.services.task_scheduler import (
    MAX_EXECUTION_MINUTES,
    _check_and_execute_due_tasks,
    _cleanup_stuck_executions,
    _has_running_execution,
    _schedule_next_run,
    execute_task_manually,
    start_scheduler,
)

# ============================================================
# start_scheduler
# ============================================================


class TestStartScheduler:
    def setup_method(self):
        # Reset global state before each test
        import apps.api.services.task_scheduler as mod

        mod._scheduler_started = False

    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_starts_scheduler_thread_once(self, mock_thread):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        start_scheduler()
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_does_not_start_again_if_already_started(self, mock_thread):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        start_scheduler()
        start_scheduler()  # Second call should be no-op
        assert mock_thread.call_count == 1


# ============================================================
# _has_running_execution
# ============================================================


class TestHasRunningExecution:
    def test_returns_false_when_no_executions(self):
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = []
        assert _has_running_execution(mock_repo, 1) is False

    def test_returns_false_when_status_not_running(self):
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = [{"status": "completed", "started_at": "2026-06-14 10:00:00"}]
        assert _has_running_execution(mock_repo, 1) is False

    def test_returns_true_when_running_within_30_minutes(self):
        recent = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = [{"status": "running", "started_at": recent}]
        assert _has_running_execution(mock_repo, 1) is True

    def test_returns_false_when_running_over_30_minutes(self):
        old = (datetime.now() - timedelta(minutes=31)).strftime("%Y-%m-%d %H:%M:%S")
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = [{"status": "running", "started_at": old}]
        assert _has_running_execution(mock_repo, 1) is False

    def test_returns_false_when_started_at_empty(self):
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = [{"status": "running", "started_at": ""}]
        assert _has_running_execution(mock_repo, 1) is False

    def test_returns_false_when_started_at_invalid_format(self):
        mock_repo = MagicMock()
        mock_repo.get_executions.return_value = [{"status": "running", "started_at": "not-a-date"}]
        assert _has_running_execution(mock_repo, 1) is False


# ============================================================
# _cleanup_stuck_executions
# ============================================================


class TestCleanupStuckExecutions:
    def test_calls_cleanup_on_repo(self):
        mock_repo = MagicMock()
        mock_repo.cleanup_stuck_executions.return_value = 3

        _cleanup_stuck_executions(mock_repo)
        mock_repo.cleanup_stuck_executions.assert_called_once_with(MAX_EXECUTION_MINUTES)

    def test_handles_exception_gracefully(self):
        mock_repo = MagicMock()
        mock_repo.cleanup_stuck_executions.side_effect = Exception("db error")

        # Should not raise
        _cleanup_stuck_executions(mock_repo)


# ============================================================
# _schedule_next_run
# ============================================================


class TestScheduleNextRun:
    def test_interval_schedule_adds_minutes(self):
        mock_repo = MagicMock()
        task = {
            "id": 1,
            "schedule_type": "interval",
            "schedule_config": json.dumps({"minutes": 30}),
        }
        _schedule_next_run(mock_repo, task)
        mock_repo.update_after_run.assert_called_once()
        args = mock_repo.update_after_run.call_args[0]
        assert args[0] == 1  # task_id
        # next_run should be ~30 minutes from now
        next_run = datetime.strptime(args[1], "%Y-%m-%d %H:%M:%S")
        expected = datetime.now() + timedelta(minutes=30)
        assert abs((next_run - expected).total_seconds()) < 5

    def test_interval_schedule_default_60_minutes(self):
        mock_repo = MagicMock()
        task = {
            "id": 2,
            "schedule_type": "interval",
            "schedule_config": json.dumps({}),
        }
        _schedule_next_run(mock_repo, task)
        args = mock_repo.update_after_run.call_args[0]
        next_run = datetime.strptime(args[1], "%Y-%m-%d %H:%M:%S")
        expected = datetime.now() + timedelta(minutes=60)
        assert abs((next_run - expected).total_seconds()) < 5

    def test_non_interval_schedule_defaults_to_1_hour(self):
        mock_repo = MagicMock()
        task = {
            "id": 3,
            "schedule_type": "cron",
            "schedule_config": "{}",
        }
        _schedule_next_run(mock_repo, task)
        args = mock_repo.update_after_run.call_args[0]
        next_run = datetime.strptime(args[1], "%Y-%m-%d %H:%M:%S")
        expected = datetime.now() + timedelta(hours=1)
        assert abs((next_run - expected).total_seconds()) < 5

    def test_invalid_json_config_defaults_to_empty(self):
        mock_repo = MagicMock()
        task = {
            "id": 4,
            "schedule_type": "interval",
            "schedule_config": "not-json",
        }
        _schedule_next_run(mock_repo, task)
        args = mock_repo.update_after_run.call_args[0]
        next_run = datetime.strptime(args[1], "%Y-%m-%d %H:%M:%S")
        expected = datetime.now() + timedelta(minutes=60)
        assert abs((next_run - expected).total_seconds()) < 5

    def test_dict_config_used_directly(self):
        mock_repo = MagicMock()
        task = {
            "id": 5,
            "schedule_type": "interval",
            "schedule_config": {"minutes": 15},
        }
        _schedule_next_run(mock_repo, task)
        args = mock_repo.update_after_run.call_args[0]
        next_run = datetime.strptime(args[1], "%Y-%m-%d %H:%M:%S")
        expected = datetime.now() + timedelta(minutes=15)
        assert abs((next_run - expected).total_seconds()) < 5


# ============================================================
# _check_and_execute_due_tasks
# ============================================================


class TestCheckAndExecuteDueTasks:
    @patch("apps.api.services.task_scheduler._schedule_next_run")
    @patch("apps.api.services.task_scheduler._has_running_execution", return_value=False)
    @patch("apps.api.services.task_scheduler._cleanup_stuck_executions")
    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_creates_execution_for_due_tasks(self, mock_thread, mock_cleanup, mock_has_running, mock_schedule):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        mock_repo = MagicMock()
        mock_repo.get_due_tasks.return_value = [
            {"id": 1, "name": "task1", "task_type": "aggregate_detect"},
        ]
        mock_repo.create_execution.return_value = 100

        with patch("apps.api.database.repositories.task_repository.TaskRepository", return_value=mock_repo):
            _check_and_execute_due_tasks()

        mock_repo.create_execution.assert_called_once_with(1)
        mock_thread_instance.start.assert_called_once()
        mock_schedule.assert_called_once()

    @patch("apps.api.services.task_scheduler._schedule_next_run")
    @patch("apps.api.services.task_scheduler._has_running_execution", return_value=True)
    @patch("apps.api.services.task_scheduler._cleanup_stuck_executions")
    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_skips_task_with_running_execution(self, mock_thread, mock_cleanup, mock_has_running, mock_schedule):
        mock_repo = MagicMock()
        mock_repo.get_due_tasks.return_value = [
            {"id": 1, "name": "task1"},
        ]

        with patch("apps.api.database.repositories.task_repository.TaskRepository", return_value=mock_repo):
            _check_and_execute_due_tasks()

        mock_repo.create_execution.assert_not_called()
        # When task is skipped due to running execution, _schedule_next_run is NOT called
        mock_schedule.assert_not_called()

    @patch("apps.api.services.task_scheduler._schedule_next_run")
    @patch("apps.api.services.task_scheduler._has_running_execution", return_value=False)
    @patch("apps.api.services.task_scheduler._cleanup_stuck_executions")
    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_no_due_tasks_does_nothing(self, mock_thread, mock_cleanup, mock_has_running, mock_schedule):
        mock_repo = MagicMock()
        mock_repo.get_due_tasks.return_value = []

        with patch("apps.api.database.repositories.task_repository.TaskRepository", return_value=mock_repo):
            _check_and_execute_due_tasks()

        mock_repo.create_execution.assert_not_called()
        mock_schedule.assert_not_called()


# ============================================================
# execute_task_manually
# ============================================================


class TestExecuteTaskManually:
    @patch("apps.api.services.task_scheduler._schedule_next_run")
    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_returns_error_when_task_not_found(self, mock_thread, mock_schedule):
        mock_repo = MagicMock()
        mock_repo.get_task.return_value = None

        with patch("apps.api.database.repositories.task_repository.TaskRepository", return_value=mock_repo):
            result = execute_task_manually(999)

        assert result == {"error": "Task not found"}

    @patch("apps.api.services.task_scheduler._schedule_next_run")
    @patch("apps.api.services.task_scheduler.threading.Thread")
    def test_starts_execution_and_returns_id(self, mock_thread, mock_schedule):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        mock_repo = MagicMock()
        mock_repo.get_task.return_value = {"id": 1, "name": "task1", "task_type": "aggregate_detect"}
        mock_repo.create_execution.return_value = 42

        with patch("apps.api.database.repositories.task_repository.TaskRepository", return_value=mock_repo):
            result = execute_task_manually(1)

        assert result == {"execution_id": 42, "status": "started"}
        mock_thread_instance.start.assert_called_once()
        mock_schedule.assert_called_once()
