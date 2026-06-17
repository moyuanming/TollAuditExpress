"""后台任务调度器 — daemon 线程，定期检查到期任务并执行"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_lock = threading.Lock()

# 单次任务最长执行时长（分钟）。超过则标记为失败，避免僵尸线程/记录堆积。
# 可通过 MAX_EXECUTION_MINUTES 环境变量覆盖；默认 60 分钟对全量回填偏紧，
# 客车 OBU 全量 17k+ 候选按当前 AI service 速率需更长,推荐部署时设 360。
MAX_EXECUTION_MINUTES = int(os.getenv('MAX_EXECUTION_MINUTES', '60'))


def start_scheduler():
    """启动调度器 daemon 线程（仅启动一次）"""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="task-scheduler")
    thread.start()
    logger.info("Task scheduler started")


def _scheduler_loop():
    """调度器主循环：每30秒检查一次到期任务"""
    while True:
        try:
            _check_and_execute_due_tasks()
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)
        time.sleep(30)


def _check_and_execute_due_tasks():
    """检查并执行到期任务"""
    from apps.api.database.repositories.task_repository import TaskRepository

    task_repo = TaskRepository()
    _cleanup_stuck_executions(task_repo)
    due_tasks = task_repo.get_due_tasks()

    for task in due_tasks:
        task_id = task['id']
        task_name = task.get('name', '')

        if _has_running_execution(task_repo, task_id):
            continue

        logger.info("Executing task [%d] %s", task_id, task_name)
        execution_id = task_repo.create_execution(task_id)

        t = threading.Thread(
            target=_execute_and_record,
            args=(task, execution_id),
            daemon=True,
            name=f"task-exec-{task_id}"
        )
        t.start()

        _schedule_next_run(task_repo, task)


def _has_running_execution(task_repo, task_id: int) -> bool:
    """检查任务是否有正在运行的执行（30分钟内视为活跃）"""
    executions = task_repo.get_executions(task_id, limit=1)
    if executions and executions[0].get('status') == 'running':
        started = executions[0].get('started_at', '')
        if started:
            try:
                start_dt = datetime.strptime(started, '%Y-%m-%d %H:%M:%S')
                return datetime.now() - start_dt < timedelta(minutes=30)
            except (ValueError, TypeError):
                pass
    return False


def _cleanup_stuck_executions(task_repo):
    """将超时未结束的 running 记录标记为 failed，限制线程/记录堆积"""
    try:
        cleaned = task_repo.cleanup_stuck_executions(MAX_EXECUTION_MINUTES)
        if cleaned:
            logger.warning("清理 %d 条超时未结束的任务执行记录（> %d 分钟）",
                           cleaned, MAX_EXECUTION_MINUTES)
    except Exception as e:
        logger.error("清理超时任务失败: %s", e, exc_info=True)


def _execute_and_record(task: dict, execution_id: int):
    """执行任务并记录结果（带实时日志落库）"""
    import logging
    import threading

    from apps.api.services.task_executor import (
        clear_log_context,
        execute_task,
        get_log_lines,
        set_log_context,
    )

    # 安装日志捕获 handler(仅本线程执行期间有效)
    capture = __import__(
        'apps.api.services.task_executor', fromlist=['_CaptureHandler']
    )._CaptureHandler(level=logging.INFO)
    capture.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))
    root = logging.getLogger()
    root.addHandler(capture)
    # uvicorn 把 root level 设为 WARNING,会把 INFO 过滤掉导致 capture handler 收不到
    # 子 logger 的 INFO 记录。临时降到 INFO 即可。
    _original_root_level = root.level
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    set_log_context(execution_id)

    # 周期落库线程：每 5 秒把当前缓冲刷一次到 DB，让前端能实时看到进度
    stop_event = threading.Event()

    def _log_flusher():
        from apps.api.database.repositories.task_repository import TaskRepository
        repo = TaskRepository()
        while not stop_event.wait(5):
            try:
                lines = get_log_lines(execution_id)
                if lines:
                    repo.update_execution_logs(execution_id, "\n".join(lines[-2000:]))
            except Exception as e:
                logger.warning("周期落库日志失败: %s", e)

    flusher = threading.Thread(target=_log_flusher, daemon=True,
                               name=f"task-log-flusher-{execution_id}")
    flusher.start()

    task_type = task.get('task_type', 'aggregate_detect')
    task_name = task.get('name', f'task#{task.get("id")}')
    logger.info("Task [%d] %s started (type=%s)", task['id'], task_name, task_type)

    try:
        from apps.api.database.repositories.task_repository import TaskRepository
        task_repo = TaskRepository()
        result = execute_task(task)
        task_repo.complete_execution(
            execution_id, result_summary=result, error_message=None,
        )
        logger.info("Task [%d] completed: %s", task['id'], result)
    except Exception as e:
        logger.error("Task [%d] failed: %s", task['id'], e, exc_info=True)
        try:
            from apps.api.database.repositories.task_repository import TaskRepository
            TaskRepository().complete_execution(execution_id, error_message=str(e))
        except Exception:
            pass
    finally:
        stop_event.set()
        try:
            lines = get_log_lines(execution_id)
            if lines:
                tail = "\n".join(lines[-2000:])
                TaskRepository().update_execution_logs(execution_id, tail)
        except Exception as e:
            logger.warning("保存执行日志失败: %s", e)
        root.removeHandler(capture)
        root.setLevel(_original_root_level)
        clear_log_context(execution_id)


def _schedule_next_run(task_repo, task: dict):
    """计算并设置下次执行时间"""
    schedule_type = task.get('schedule_type', 'interval')
    config_str = task.get('schedule_config', '{}')

    try:
        config = json.loads(config_str) if isinstance(config_str, str) else config_str
    except (json.JSONDecodeError, TypeError):
        config = {}

    now = datetime.now()
    if schedule_type == 'interval':
        minutes = config.get('minutes', 60)
        next_run = now + timedelta(minutes=minutes)
    else:
        next_run = now + timedelta(hours=1)

    task_repo.update_after_run(task['id'], next_run.strftime('%Y-%m-%d %H:%M:%S'))


def execute_task_manually(task_id: int) -> dict:
    """手动执行任务（后台线程，立即返回 execution_id）"""
    from apps.api.database.repositories.task_repository import TaskRepository

    task_repo = TaskRepository()
    task = task_repo.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    execution_id = task_repo.create_execution(task_id)

    t = threading.Thread(
        target=_execute_and_record,
        args=(task, execution_id),
        daemon=True,
        name=f"task-exec-manual-{task_id}"
    )
    t.start()

    _schedule_next_run(task_repo, task)
    return {"execution_id": execution_id, "status": "started"}
