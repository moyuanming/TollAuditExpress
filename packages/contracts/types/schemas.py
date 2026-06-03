"""前后端共享 Pydantic 模型定义 — 接口契约的单一事实来源"""

from typing import Optional, List, Any
from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class ActionType(str, Enum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class TripBase(BaseModel):
    passid: str


class TripResponse(BaseModel):
    id: int
    passid: str
    entry_time: Optional[str] = None
    entry_station_name: Optional[str] = None
    entry_lane_id: Optional[str] = None
    entry_vehicle_id: Optional[str] = None
    entry_vehicle_type: Optional[int] = None
    entry_vehicle_color: Optional[int] = None
    entry_obu_id: Optional[str] = None
    entry_media_type: Optional[int] = None
    entry_image_license: Optional[str] = None
    entry_image_trans: Optional[str] = None
    exit_time: Optional[str] = None
    exit_station_name: Optional[str] = None
    exit_lane_id: Optional[str] = None
    exit_vehicle_id: Optional[str] = None
    exit_vehicle_type: Optional[int] = None
    exit_vehicle_color: Optional[int] = None
    exit_obu_id: Optional[str] = None
    exit_media_type: Optional[int] = None
    exit_image_license: Optional[str] = None
    exit_image_trans: Optional[str] = None
    gantry_count: int = 0
    audit_status: str = 'PENDING'
    risk_score: float = 0.0
    entry_visual_type: Optional[str] = None
    exit_visual_type: Optional[str] = None
    fingerprint_sim: Optional[float] = None

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    trips: List[TripResponse]
    total: int
    limit: int
    offset: int


class SuspectResponse(BaseModel):
    id: int
    audit_trip_id: int
    fraud_type: str
    passid: str
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    entry_vehicle_id: Optional[str] = None
    exit_vehicle_id: Optional[str] = None
    entry_vehicle_type: Optional[int] = None
    exit_vehicle_type: Optional[int] = None
    entry_visual_type: Optional[str] = None
    exit_visual_type: Optional[str] = None
    is_suspicious: int = 0
    risk_score: float = 0.0
    process_status: str = 'UNPROCESSED'
    details: Optional[str] = None

    class Config:
        from_attributes = True


class SuspectListResponse(BaseModel):
    suspects: List[SuspectResponse]
    total: int


class StatsResponse(BaseModel):
    total_trips: int
    verified_trips: int
    suspected_trips: int
    confirmed_fraud: int


class AggregateRequest(BaseModel):
    days: int = 7
    limit: int = 100


class ProcessRequest(BaseModel):
    action: ActionType
    operator: Optional[str] = None
    comments: Optional[str] = None


class DetectRequest(BaseModel):
    passid: str


# ---- 定时任务系统 ----


class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    task_type: str = "aggregate_detect"
    filter_rules: Optional[dict] = None
    schedule_type: str = "interval"
    schedule_config: dict


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    task_type: Optional[str] = None
    filter_rules: Optional[dict] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[dict] = None
    enabled: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    task_type: str
    filter_rules: Optional[str] = None
    schedule_type: str
    schedule_config: str
    enabled: int = 1
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int


class TaskExecutionResponse(BaseModel):
    id: int
    task_id: int
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class TaskExecutionListResponse(BaseModel):
    executions: List[TaskExecutionResponse]
    total: int
