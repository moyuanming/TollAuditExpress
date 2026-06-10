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
    gantry_records: Optional[str] = None

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    trips: List[TripResponse]
    total: int
    limit: int
    offset: int


class TripDetailResponse(TripResponse):
    """行程详情（含门架图片流水与该行程触发的所有稽核结果）"""
    gantry_image_records: Optional[str] = None
    audit_results: List["SuspectResponse"] = []


class SuspectResponse(BaseModel):
    id: int
    audit_trip_id: int
    fraud_type: str
    passid: str
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    entry_station_name: Optional[str] = None
    exit_station_name: Optional[str] = None
    entry_lane_id: Optional[str] = None
    exit_lane_id: Optional[str] = None
    entry_vehicle_id: Optional[str] = None
    exit_vehicle_id: Optional[str] = None
    entry_vehicle_type: Optional[int] = None
    exit_vehicle_type: Optional[int] = None
    entry_vehicle_color: Optional[int] = None
    exit_vehicle_color: Optional[int] = None
    entry_obu_id: Optional[str] = None
    exit_obu_id: Optional[str] = None
    entry_media_type: Optional[int] = None
    exit_media_type: Optional[int] = None
    entry_image_license: Optional[str] = None
    entry_image_trans: Optional[str] = None
    exit_image_license: Optional[str] = None
    exit_image_trans: Optional[str] = None
    entry_visual_type: Optional[str] = None
    exit_visual_type: Optional[str] = None
    entry_color: Optional[str] = None
    exit_color: Optional[str] = None
    is_suspicious: int = 0
    risk_score: float = 0.0
    process_status: str = 'UNPROCESSED'
    details: Optional[str] = None
    gantry_count: int = 0
    gantry_records: Optional[str] = None
    gantry_image_records: Optional[str] = None
    # LLM 二次判定结果（由 llm_batch.py 写入；未判定时为 None）
    llm_is_same_vehicle: Optional[int] = None
    llm_confidence: Optional[float] = None
    llm_reason: Optional[str] = None
    llm_model: Optional[str] = None
    llm_checked_at: Optional[str] = None

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


# ---- 车辆查询（原始 Doris 数据）----


class RawTripResponse(BaseModel):
    """来自 Doris 原始表的行程聚合结果（不含检测后字段）"""
    passid: str
    entry_time: Optional[str] = None
    entry_station_name: Optional[str] = None
    entry_vehicle_id: Optional[str] = None
    entry_vehicle_color: Optional[str] = None
    entry_vehicle_type: Optional[int] = None
    entry_obu_id: Optional[str] = None
    exit_time: Optional[str] = None
    exit_station_name: Optional[str] = None
    exit_vehicle_id: Optional[str] = None
    exit_vehicle_color: Optional[str] = None
    exit_vehicle_type: Optional[int] = None
    exit_obu_id: Optional[str] = None
    gantry_count: int = 0


class RawTripListResponse(BaseModel):
    trips: List[RawTripResponse]
    total: int
    limit: int
    offset: int


class RawTripDetailResponse(RawTripResponse):
    """原始数据视角下的行程详情（无 audit_results）"""
    entry_lane_id: Optional[str] = None
    exit_lane_id: Optional[str] = None
    entry_image_license: Optional[str] = None
    entry_image_trans: Optional[str] = None
    exit_image_license: Optional[str] = None
    exit_image_trans: Optional[str] = None
    gantry_records: Optional[str] = None
    gantry_image_records: Optional[str] = None


# ---- MaaS 出入口车辆双图比对 ----


class DetectEntryExitLLMRequest(BaseModel):
    """手动触发 MaaS 双图比对的请求体（车牌特写 image_license）。"""
    passid: str


class LlmVehicleCompareResponse(BaseModel):
    """MaaS 双图比对响应。结构化 JSON 由 LLM 输出，前端可渲染置信度与依据。"""
    passid: str
    is_same_vehicle: bool
    confidence: float
    reason: str
    entry_image_url: Optional[str] = None
    exit_image_url: Optional[str] = None
    model: str
    elapsed_ms: int


TripDetailResponse.model_rebuild()


TripDetailResponse.model_rebuild()
