"""后台任务调度器 — daemon 线程，定期检查到期任务并执行"""

import threading
import logging
import time
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_lock = threading.Lock()


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


def _execute_and_record(task: dict, execution_id: int):
    """执行任务并记录结果"""
    try:
        from apps.api.database.repositories.task_repository import TaskRepository
        from apps.api.services.task_executor import execute_task

        task_repo = TaskRepository()
        result = execute_task(task)
        task_repo.complete_execution(execution_id, result_summary=result)
        logger.info("Task [%d] completed: %s", task['id'], result)
    except Exception as e:
        logger.error("Task [%d] failed: %s", task['id'], e)
        try:
            from apps.api.database.repositories.task_repository import TaskRepository
            TaskRepository().complete_execution(execution_id, error_message=str(e))
        except Exception:
            pass


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
