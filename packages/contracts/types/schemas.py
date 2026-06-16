"""前后端共享 Pydantic 模型定义 — 接口契约的单一事实来源"""

import re
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ActionType(str, Enum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class TripBase(BaseModel):
    passid: str


class TripResponse(BaseModel):
    id: int
    passid: str
    entry_time: str | None = None
    entry_station_name: str | None = None
    entry_lane_id: str | None = None
    entry_vehicle_id: str | None = None
    entry_vehicle_type: int | None = None
    entry_vehicle_color: int | None = None
    entry_obu_id: str | None = None
    entry_media_type: int | None = None
    entry_image_license: str | None = None
    entry_image_trans: str | None = None
    exit_time: str | None = None
    exit_station_name: str | None = None
    exit_lane_id: str | None = None
    exit_vehicle_id: str | None = None
    exit_vehicle_type: int | None = None
    exit_vehicle_color: int | None = None
    exit_obu_id: str | None = None
    exit_media_type: int | None = None
    exit_image_license: str | None = None
    exit_image_trans: str | None = None
    gantry_count: int = 0
    audit_status: str = "PENDING"
    risk_score: float = 0.0
    entry_visual_type: str | None = None
    exit_visual_type: str | None = None
    fingerprint_sim: float | None = None
    gantry_records: str | None = None

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    trips: list[TripResponse]
    total: int
    limit: int
    offset: int


class TripDetailResponse(TripResponse):
    """行程详情（含门架图片流水与该行程触发的所有稽核结果）"""

    gantry_image_records: str | None = None
    audit_results: list["SuspectResponse"] = []


class SuspectResponse(BaseModel):
    id: int
    audit_trip_id: int
    fraud_type: str
    passid: str
    entry_time: str | None = None
    exit_time: str | None = None
    entry_station_name: str | None = None
    exit_station_name: str | None = None
    entry_lane_id: str | None = None
    exit_lane_id: str | None = None
    entry_vehicle_id: str | None = None
    exit_vehicle_id: str | None = None
    entry_vehicle_type: int | None = None
    exit_vehicle_type: int | None = None
    entry_vehicle_color: int | None = None
    exit_vehicle_color: int | None = None
    entry_obu_id: str | None = None
    exit_obu_id: str | None = None
    entry_media_type: int | None = None
    exit_media_type: int | None = None
    entry_image_license: str | None = None
    entry_image_trans: str | None = None
    exit_image_license: str | None = None
    exit_image_trans: str | None = None
    entry_visual_type: str | None = None
    exit_visual_type: str | None = None
    entry_color: str | None = None
    exit_color: str | None = None
    is_suspicious: int = 0
    risk_score: float = 0.0
    process_status: str = "UNPROCESSED"
    details: str | None = None
    gantry_count: int = 0
    gantry_records: str | None = None
    gantry_image_records: str | None = None
    # LLM 二次判定结果（由 llm_batch.py 写入；未判定时为 None）
    llm_is_same_vehicle: int | None = None
    llm_confidence: float | None = None
    llm_reason: str | None = None
    llm_model: str | None = None
    llm_checked_at: str | None = None

    class Config:
        from_attributes = True


class SuspectListResponse(BaseModel):
    suspects: list[SuspectResponse]
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
    operator: str | None = None
    comments: str | None = None


class DetectRequest(BaseModel):
    passid: str


# ---- 定时任务系统 ----


class TaskCreate(BaseModel):
    name: str
    description: str | None = None
    task_type: str = "aggregate_detect"
    filter_rules: dict | None = None
    schedule_type: str = "interval"
    schedule_config: dict


class TaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    task_type: str | None = None
    filter_rules: dict | None = None
    schedule_type: str | None = None
    schedule_config: dict | None = None
    enabled: bool | None = None


class TaskResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    task_type: str
    filter_rules: str | None = None
    schedule_type: str
    schedule_config: str
    enabled: int = 1
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


class TaskExecutionResponse(BaseModel):
    id: int
    task_id: int
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    result_summary: str | None = None
    error_message: str | None = None
    logs: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class TaskExecutionListResponse(BaseModel):
    executions: list[TaskExecutionResponse]
    total: int


# ---- 车辆查询（原始 Doris 数据）----


class RawTripResponse(BaseModel):
    """来自 Doris 原始表的行程聚合结果（不含检测后字段）"""

    passid: str
    entry_time: str | None = None
    entry_station_name: str | None = None
    entry_vehicle_id: str | None = None
    entry_vehicle_color: str | None = None
    entry_vehicle_type: int | None = None
    entry_obu_id: str | None = None
    exit_time: str | None = None
    exit_station_name: str | None = None
    exit_vehicle_id: str | None = None
    exit_vehicle_color: str | None = None
    exit_vehicle_type: int | None = None
    exit_obu_id: str | None = None
    gantry_count: int = 0


class RawTripListResponse(BaseModel):
    trips: list[RawTripResponse]
    total: int
    limit: int
    offset: int


class RawTripDetailResponse(RawTripResponse):
    """原始数据视角下的行程详情（无 audit_results）"""

    entry_lane_id: str | None = None
    exit_lane_id: str | None = None
    entry_image_license: str | None = None
    entry_image_trans: str | None = None
    exit_image_license: str | None = None
    exit_image_trans: str | None = None
    gantry_records: str | None = None
    gantry_image_records: str | None = None


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
    entry_image_url: str | None = None
    exit_image_url: str | None = None
    model: str
    elapsed_ms: int
    plate_match: bool | None = None
    plate_recognized_entry: str | None = None
    plate_recognized_exit: str | None = None


class DetectionRuleCreate(BaseModel):
    name: str
    fraud_type: str
    severity: int = 2
    description: str | None = None
    rule_expr: dict
    threshold: float = 0.5
    dry_run: int = 0
    source: str = "manual"


class DetectionRuleUpdate(BaseModel):
    name: str | None = None
    fraud_type: str | None = None
    severity: int | None = None
    description: str | None = None
    rule_expr: dict | None = None
    threshold: float | None = None
    dry_run: int | None = None
    enabled: int | None = None


class DetectionRuleResponse(BaseModel):
    id: int
    name: str
    fraud_type: str
    severity: int = 2
    description: str | None = None
    rule_expr: str
    threshold: float = 0.5
    dry_run: int = 0
    enabled: int = 1
    source: str = "manual"
    created_at: str | None = None
    updated_at: str | None = None


class DetectionRuleListResponse(BaseModel):
    rules: list
    total: int


TripDetailResponse.model_rebuild()


TripDetailResponse.model_rebuild()


# ---- 客车 OBU 监测（PASSENGER_USES_TRUCK_OBU_NON_NEW_A）----


class PassengerObuDailyStat(BaseModel):
    """客车 OBU 监测 — 每日统计条目"""

    date: str  # YYYY-MM-DD
    fraud_type: str
    scanned_count: int = 0
    suspicious_count: int = 0
    confirmed_count: int = 0
    last_run_at: str | None = None


class PassengerObuDailyStatListResponse(BaseModel):
    stats: list[PassengerObuDailyStat]
    total: int


class PassengerObuAnomalyItem(BaseModel):
    """客车 OBU 监测 — 异常条目（响应），含 source_side（ENTRY/EXIT/BOTH）+ LLM 复核字段"""

    id: int
    audit_trip_id: int
    fraud_type: str
    passid: str | None = None
    entry_time: str | None = None
    exit_time: str | None = None
    entry_station_name: str | None = None
    exit_station_name: str | None = None
    entry_vehicle_id: str | None = None
    exit_vehicle_id: str | None = None
    entry_vehicle_type: int | None = None
    exit_vehicle_type: int | None = None
    entry_obu_id: str | None = None
    exit_obu_id: str | None = None
    entry_media_type: int | None = None
    exit_media_type: int | None = None
    is_suspicious: int = 1
    risk_score: float = 0.85
    process_status: str = "UNPROCESSED"
    details: str | None = None
    source_side: str | None = None
    visual_vehicle_type: str | None = None
    llm_verified: bool | None = None
    llm_confidence: float | None = None
    llm_call_status: str | None = None
    entry_image_trans: str | None = None
    exit_image_trans: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class PassengerObuAnomalyListResponse(BaseModel):
    anomalies: list[PassengerObuAnomalyItem]
    total: int
    limit: int
    offset: int


class PassengerObuOverviewResponse(BaseModel):
    """客车 OBU 监测 — 顶部卡片：累计扫描 / 异常 / 待处理 / 已确认 + 最近 30 天趋势"""

    total_scanned: int = 0
    total_suspicious: int = 0
    total_pending: int = 0
    total_confirmed: int = 0
    last_run_at: str | None = None
    last_30_days: list[PassengerObuDailyStat] = []


# ---- 公开落地页线索 (landing) ----


class LandingLeadCreate(BaseModel):
    """公开落地页表单 — 客户线索入库请求体。"""

    name: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    org: str = Field(..., min_length=1, max_length=100)
    email: EmailStr | None = None
    message: str | None = Field(None, max_length=500)
    source: str = Field("landing-page", max_length=32)

    @field_validator("name", "org")
    @classmethod
    def _strip_nonblank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        if v is None or v == "":
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class LandingLeadResponse(BaseModel):
    id: int
    name: str
    phone: str
    org: str
    email: str | None = None
    message: str | None = None
    source: str
    ip: str | None = None
    ua: str | None = None
    created_at: str


class LandingLeadListResponse(BaseModel):
    leads: list["LandingLeadResponse"]
    total: int
    limit: int
    offset: int
