"""定时任务 API 路由"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from apps.api.database.repositories.task_repository import TaskRepository
from apps.api.services.task_scheduler import execute_task_manually
from packages.contracts.types.schemas import (
    TaskCreate, TaskUpdate,
    TaskResponse, TaskListResponse,
    TaskExecutionResponse, TaskExecutionListResponse
)

router = APIRouter()


@router.get("/tasks", response_model=TaskListResponse)
async def get_tasks():
    """获取任务列表"""
    repo = TaskRepository()
    tasks = repo.get_tasks()
    return TaskListResponse(tasks=tasks, total=len(tasks))


@router.post("/tasks", status_code=201, response_model=TaskResponse)
async def create_task(data: TaskCreate):
    """创建定时任务"""
    repo = TaskRepository()
    task_id = repo.create_task(data.dict())
    task = repo.get_task(task_id)
    return TaskResponse(**task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """获取任务详情"""
    repo = TaskRepository()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**task)


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, data: TaskUpdate):
    """更新任务"""
    repo = TaskRepository()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = {k: v for k, v in data.dict().items() if v is not None}
    if updates:
        repo.update_task(task_id, updates)
    task = repo.get_task(task_id)
    return TaskResponse(**task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    """删除任务"""
    repo = TaskRepository()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    repo.delete_task(task_id)
    return {"message": "Task deleted"}


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: int):
    """手动立即执行任务"""
    repo = TaskRepository()
    task = repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = execute_task_manually(task_id)
    return result


@router.get("/tasks/{task_id}/executions", response_model=TaskExecutionListResponse)
async def get_task_executions(task_id: int, limit: int = 50):
    """获取任务执行历史"""
    repo = TaskRepository()
    executions = repo.get_executions(task_id, limit=limit)
    total = repo.get_executions_count(task_id)
    return TaskExecutionListResponse(executions=executions, total=total)
