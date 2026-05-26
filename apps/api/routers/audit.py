"""稽核系统 API 路由"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional
import uuid
import json

from apps.api.services.trip_aggregator import TripAggregator
from apps.api.services.truck_obu_detector import TruckOBUDetector
from apps.api.services.entry_exit_matcher import EntryExitMatcher
from apps.api.database.repositories.trip_repository import TripRepository
from apps.api.database.repositories.audit_repository import AuditRepository
from apps.api.models.schemas import (
    TripResponse, TripListResponse, SuspectResponse, SuspectListResponse,
    StatsResponse, AggregateRequest, ProcessRequest
)

router = APIRouter()

# 全局检测器实例
truck_detector = None
entry_exit_matcher = None
aggregation_tasks = {}


def get_truck_detector():
    global truck_detector
    if truck_detector is None:
        truck_detector = TruckOBUDetector()
    return truck_detector


def get_entry_exit_matcher():
    global entry_exit_matcher
    if entry_exit_matcher is None:
        entry_exit_matcher = EntryExitMatcher()
    return entry_exit_matcher


@router.get("/stats/overview", response_model=StatsResponse)
async def get_stats():
    """获取稽核概览统计"""
    repo = TripRepository()
    stats = repo.get_stats()
    return StatsResponse(**stats)


@router.get("/trips", response_model=TripListResponse)
async def get_trips(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """获取行程列表"""
    repo = TripRepository()
    trips = repo.get_trips(status=status, limit=limit, offset=offset)
    total = repo.get_total_count(status=status)
    return TripListResponse(trips=trips, total=total, limit=limit, offset=offset)


@router.get("/trip/{passid}", response_model=TripResponse)
async def get_trip(passid: str):
    """获取行程详情"""
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripResponse(**trip)


@router.post("/trips/aggregate")
async def aggregate_trips(background_tasks: BackgroundTasks, request: AggregateRequest):
    """启动批量聚合行程任务"""
    task_id = str(uuid.uuid4())
    
    def run_aggregation():
        aggregator = TripAggregator()
        total = aggregator.aggregate_recent_trips(
            days=request.days,
            limit=request.limit,
            on_progress=lambda p: aggregation_tasks.update({task_id: p})
        )
        aggregation_tasks[task_id] = {"status": "completed", "total": total}
    
    background_tasks.add_task(run_aggregation)
    
    return {
        "task_id": task_id,
        "status": "started",
        "message": "Aggregation task started"
    }


@router.get("/trips/aggregate/{task_id}")
async def get_aggregation_status(task_id: str):
    """获取聚合任务状态"""
    status = aggregation_tasks.get(task_id, {"status": "not_found"})
    return status


@router.post("/trips/aggregate/{task_id}/stop")
async def stop_aggregation(task_id: str):
    """停止聚合任务"""
    if task_id in aggregation_tasks:
        aggregation_tasks[task_id]["status"] = "stopped"
    return {"message": "Task stop requested"}


@router.get("/trips/aggregate/stream/{task_id}")
async def stream_aggregation(task_id: str):
    """SSE流式推送聚合进度"""
    async def event_generator():
        while True:
            if task_id in aggregation_tasks:
                status = aggregation_tasks[task_id]
                yield f"data: {json.dumps(status)}\n\n"
                if status.get("status") in ["completed", "stopped", "error"]:
                    break
            import time
            time.sleep(0.5)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/suspects", response_model=SuspectListResponse)
async def get_suspects(limit: int = 100, offset: int = 0):
    """获取可疑记录列表"""
    repo = AuditRepository()
    suspects = repo.get_suspects(limit=limit, offset=offset)
    total = repo.get_suspects_count()
    return SuspectListResponse(suspects=suspects, total=total)


@router.get("/suspect/{suspect_id}", response_model=SuspectResponse)
async def get_suspect(suspect_id: int):
    """获取可疑记录详情"""
    repo = AuditRepository()
    suspect = repo.get_suspect_detail(suspect_id)
    if not suspect:
        raise HTTPException(status_code=404, detail="Suspect not found")
    return SuspectResponse(**suspect)


@router.post("/suspect/{suspect_id}/process")
async def process_suspect(suspect_id: int, request: ProcessRequest):
    """处理可疑记录"""
    repo = AuditRepository()
    repo.update_process_status(suspect_id, request.action, request.operator, request.comments)
    return {"message": "Processed successfully"}


@router.post("/detect/truck-obu")
async def detect_truck_obu(passid: str):
    """检测货车套用客车OBU"""
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    detector = get_truck_detector()
    entry_record = {
        'VEHICLETYPE': trip.get('entry_vehicle_type'),
        'image_trans': trip.get('entry_image_trans')
    }
    result = detector.detect(entry_record)
    
    if result.get('is_suspicious'):
        audit_repo = AuditRepository()
        audit_repo.save_result({
            'audit_trip_id': trip['id'],
            'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
            'entry_vehicle_type': trip.get('entry_vehicle_type'),
            'entry_visual_type': result.get('visual_vehicle_type'),
            'is_suspicious': 1,
            'risk_score': result.get('confidence', 0),
            'details': json.dumps(result)
        })
    
    return result


@router.post("/detect/entry-exit")
async def detect_entry_exit(passid: str):
    """检测出入口车辆不一致"""
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    matcher = get_entry_exit_matcher()
    entry_record = {'image_license': trip.get('entry_image_license')}
    exit_record = {'image_license': trip.get('exit_image_license')}
    result = matcher.compare(entry_record, exit_record)
    
    if result.get('is_suspicious'):
        audit_repo = AuditRepository()
        audit_repo.save_result({
            'audit_trip_id': trip['id'],
            'fraud_type': 'ENTRY_EXIT_MISMATCH',
            'entry_visual_type': result.get('entry_visual_type'),
            'exit_visual_type': result.get('exit_visual_type'),
            'entry_color': result.get('entry_color'),
            'exit_color': result.get('exit_color'),
            'is_suspicious': 1,
            'risk_score': result.get('fingerprint_sim', 0),
            'details': json.dumps(result)
        })
    
    return result
