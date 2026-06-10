"""定时任务数据访问层"""

from typing import Optional, List, Dict
import json
from datetime import datetime

from apps.api.database.doris_connection import get_connection


class TaskRepository:
    """定时任务仓储"""

    def create_task(self, task_data: Dict) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            filter_rules = json.dumps(task_data.get('filter_rules', {})) if task_data.get('filter_rules') else None
            schedule_config = json.dumps(task_data.get('schedule_config', {}))

            cursor.execute("""
                INSERT INTO scheduled_tasks (name, description, task_type, filter_rules,
                    schedule_type, schedule_config, next_run_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                task_data['name'],
                task_data.get('description'),
                task_data.get('task_type', 'aggregate_detect'),
                filter_rules,
                task_data.get('schedule_type', 'interval'),
                schedule_config,
                now,
                now,
                now
            ))
            conn.commit()
            return cursor.lastrowid

    def get_tasks(self) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_task(self, task_id: int) -> Optional[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_tasks WHERE id = %s", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_task(self, task_id: int, updates: Dict) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            fields = []
            values = []

            if 'name' in updates:
                fields.append("name = %s")
                values.append(updates['name'])
            if 'description' in updates:
                fields.append("description = %s")
                values.append(updates['description'])
            if 'task_type' in updates:
                fields.append("task_type = %s")
                values.append(updates['task_type'])
            if 'filter_rules' in updates:
                rules = updates['filter_rules']
                values.append(json.dumps(rules) if rules else None)
                fields.append("filter_rules = %s")
            if 'schedule_type' in updates:
                fields.append("schedule_type = %s")
                values.append(updates['schedule_type'])
            if 'schedule_config' in updates:
                values.append(json.dumps(updates['schedule_config']))
                fields.append("schedule_config = %s")
            if 'enabled' in updates:
                fields.append("enabled = %s")
                values.append(1 if updates['enabled'] else 0)

            if not fields:
                return False

            fields.append("updated_at = %s")
            values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            values.append(task_id)

            cursor.execute(f"UPDATE scheduled_tasks SET {', '.join(fields)} WHERE id = %s", values)
            conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM task_executions WHERE task_id = %s", (task_id,))
            cursor.execute("DELETE FROM scheduled_tasks WHERE id = %s", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_due_tasks(self) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "SELECT * FROM scheduled_tasks WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= %s",
                (now,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_after_run(self, task_id: int, next_run_at: str):
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "UPDATE scheduled_tasks SET last_run_at = %s, next_run_at = %s, updated_at = %s WHERE id = %s",
                (now, next_run_at, now, task_id)
            )
            conn.commit()

    def create_execution(self, task_id: int) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "INSERT INTO task_executions (task_id, status, started_at) VALUES (%s, 'running', %s)",
                (task_id, now)
            )
            conn.commit()
            return cursor.lastrowid

    def complete_execution(self, execution_id: int, result_summary: Optional[Dict] = None, error_message: Optional[str] = None):
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            status = 'failed' if error_message else 'completed'
            summary = json.dumps(result_summary) if result_summary else None
            cursor.execute(
                "UPDATE task_executions SET status = %s, completed_at = %s, result_summary = %s, error_message = %s WHERE id = %s",
                (status, now, summary, error_message, execution_id)
            )
            conn.commit()

    def get_executions(self, task_id: int, limit: int = 50) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM task_executions WHERE task_id = %s ORDER BY started_at DESC LIMIT %s",
                (task_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_executions_count(self, task_id: int) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM task_executions WHERE task_id = %s", (task_id,))
            return cursor.fetchone()['count']
