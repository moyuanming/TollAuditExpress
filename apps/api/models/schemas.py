"""Pydantic 模型定义"""

from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import datetime


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
    action: str
    operator: Optional[str] = None
    comments: Optional[str] = None
