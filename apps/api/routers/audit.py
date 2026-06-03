"""稽核系统 API 路由"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
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
    StatsResponse, AggregateRequest, ProcessRequest, DetectRequest
)

router = APIRouter()


def get_truck_detector(request: Request):
    if request.app.state.truck_detector is None:
        request.app.state.truck_detector = TruckOBUDetector()
    return request.app.state.truck_detector


def get_entry_exit_matcher(request: Request):
    if request.app.state.entry_exit_matcher is None:
        request.app.state.entry_exit_matcher = EntryExitMatcher()
    return request.app.state.entry_exit_matcher


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
    offset: int = 0,
    entry_station: Optional[str] = None,
    exit_station: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
):
    """获取行程列表"""
    repo = TripRepository()
    trips = repo.get_trips(status=status, limit=limit, offset=offset,
                           entry_station=entry_station, exit_station=exit_station,
                           start_time=start_time, end_time=end_time)
    total = repo.get_total_count(status=status,
                                 entry_station=entry_station, exit_station=exit_station,
                                 start_time=start_time, end_time=end_time)
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
async def aggregate_trips(request: AggregateRequest, req: Request, background_tasks: BackgroundTasks):
    """启动批量聚合行程任务"""
    task_id = str(uuid.uuid4())
    req.app.state.aggregation_tasks[task_id] = {
        "status": "running",
        "current": 0,
        "total": 0,
        "count": 0,
        "passid": ""
    }

    def run_aggregation():
        aggregator = TripAggregator()
        try:
            total = aggregator.aggregate_recent_trips(
                days=request.days,
                limit=request.limit,
                on_progress=lambda p: req.app.state.aggregation_tasks.update({task_id: {
                    "status": "running",
                    "current": p["current"],
                    "total": p["total"],
                    "count": p["count"],
                    "passid": p["passid"]
                }}),
                run_detection=True
            )
            req.app.state.aggregation_tasks[task_id] = {
                "status": "completed",
                "current": total,
                "total": total,
                "count": total,
                "passid": ""
            }
        except Exception as e:
            req.app.state.aggregation_tasks[task_id] = {
                "status": "error",
                "message": str(e)
            }

    background_tasks.add_task(run_aggregation)
    return {"task_id": task_id, "status": "started"}


@router.get("/trips/aggregate/{task_id}")
async def get_aggregation_status(task_id: str, request: Request):
    """获取聚合任务状态"""
    status = request.app.state.aggregation_tasks.get(task_id, {"status": "not_found"})
    return status


@router.post("/trips/aggregate/{task_id}/stop")
async def stop_aggregation(task_id: str, request: Request):
    """停止聚合任务"""
    if task_id in request.app.state.aggregation_tasks:
        request.app.state.aggregation_tasks[task_id]["status"] = "stopped"
    return {"message": "Task stop requested"}


@router.get("/trips/aggregate/stream/{task_id}")
async def stream_aggregation(task_id: str, request: Request):
    """SSE流式推送聚合进度"""
    async def event_generator():
        while True:
            if task_id in request.app.state.aggregation_tasks:
                status = request.app.state.aggregation_tasks[task_id]
                yield f"data: {json.dumps(status)}\n\n"
                if status.get("status") in ["completed", "stopped", "error"]:
                    break
            import asyncio
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/suspects", response_model=SuspectListResponse)
async def get_suspects(
    fraud_type: Optional[str] = None,
    process_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """获取可疑记录列表"""
    repo = AuditRepository()
    suspects = repo.get_suspects(fraud_type=fraud_type, process_status=process_status, limit=limit, offset=offset)
    total = repo.get_suspects_count(fraud_type=fraud_type, process_status=process_status)
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
async def detect_truck_obu(detect_req: DetectRequest, request: Request):
    """检测货车套用客车OBU"""
    passid = detect_req.passid
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    detector = get_truck_detector(request)
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
async def detect_entry_exit(detect_req: DetectRequest, request: Request):
    """检测出入口车辆不一致"""
    passid = detect_req.passid
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    matcher = get_entry_exit_matcher(request)
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


@router.post("/trips/re-detect")
async def re_detect_trips(request: Request, background_tasks: BackgroundTasks):
    """补检测：对缺失视觉识别结果的行程重新运行检测"""
    task_id = str(uuid.uuid4())
    request.app.state.aggregation_tasks[task_id] = {
        "status": "running",
        "current": 0,
        "total": 0,
        "count": 0,
        "passid": ""
    }

    def run_re_detect():
        repo = TripRepository()
        trips = repo.get_trips_without_visual(limit=500)
        total = len(trips)
        count = 0

        for i, trip in enumerate(trips):
            trip_id = trip['id']
            results_to_save = []

            if trip.get('entry_vehicle_type') == 1 and trip.get('entry_image_trans'):
                try:
                    detector = get_truck_detector(request)
                    entry_record = {
                        'VEHICLETYPE': trip.get('entry_vehicle_type'),
                        'image_trans': trip.get('entry_image_trans')
                    }
                    r = detector.detect(entry_record)
                    if r.get('visual_vehicle_type'):
                        is_sus = 1 if r.get('is_suspicious') else 0
                        results_to_save.append({
                            'audit_trip_id': trip_id,
                            'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
                            'entry_vehicle_type': trip.get('entry_vehicle_type'),
                            'entry_visual_type': r.get('visual_vehicle_type'),
                            'is_suspicious': is_sus,
                            'risk_score': r.get('confidence', 0) if is_sus else 0,
                            'details': json.dumps(r)
                        })
                except Exception:
                    pass

            if trip.get('entry_image_license') and trip.get('exit_image_license'):
                try:
                    matcher = get_entry_exit_matcher(request)
                    entry_rec = {'image_license': trip.get('entry_image_license')}
                    exit_rec = {'image_license': trip.get('exit_image_license')}
                    r = matcher.compare(entry_rec, exit_rec)
                    if r.get('_comparison_success') or r.get('fingerprint_sim'):
                        results_to_save.append({
                            'audit_trip_id': trip_id,
                            'fraud_type': 'ENTRY_EXIT_MISMATCH',
                            'entry_visual_type': r.get('entry_visual_type'),
                            'exit_visual_type': r.get('exit_visual_type'),
                            'entry_color': r.get('entry_color'),
                            'exit_color': r.get('exit_color'),
                            'is_suspicious': 1 if r.get('is_suspicious') else 0,
                            'risk_score': r.get('fingerprint_sim', 0),
                            'details': json.dumps(r)
                        })
                except Exception:
                    pass

            if results_to_save:
                try:
                    repo.save_trip_with_detection_results(trip_id, trip['passid'], results_to_save)
                    count += 1
                except Exception:
                    pass

            request.app.state.aggregation_tasks[task_id] = {
                "status": "running",
                "current": i + 1,
                "total": total,
                "count": count,
                "passid": trip['passid']
            }

        request.app.state.aggregation_tasks[task_id] = {
            "status": "completed",
            "current": total,
            "total": total,
            "count": count,
            "passid": ""
        }

    background_tasks.add_task(run_re_detect)
    return {"task_id": task_id, "status": "started"}
