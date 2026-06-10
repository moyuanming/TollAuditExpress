"""稽核系统 API 路由"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import StreamingResponse, Response
from starlette.concurrency import run_in_threadpool
import httpx
from typing import Optional
import uuid
import json

from apps.api.core.logging_config import get_logger

from apps.api.services.trip_aggregator import (
    TripAggregator, get_gantry_images_by_vehicle, serialize_gantry_image_records
)
from apps.api.services.doris_trip_query import (
    query_trips as doris_query_trips,
    get_trip_detail as doris_get_trip_detail,
    SORTABLE_COLUMNS_DORIS,
    VEHICLE_ID_MATCH_MODES_DORIS,
)
from apps.api.services.truck_obu_detector import TruckOBUDetector
from apps.api.services.entry_exit_matcher import EntryExitMatcher
from apps.api.services.vehicle_comparator import compare_vehicles_by_passid
from apps.api.database.repositories.trip_repository import (
    TripRepository, SORTABLE_COLUMNS, VEHICLE_TYPE_VALUES, VEHICLE_ID_MATCH_MODES,
)
from apps.api.database.repositories.audit_repository import AuditRepository
from apps.api.models.schemas import (
    TripResponse, TripListResponse, TripDetailResponse, SuspectResponse, SuspectListResponse,
    StatsResponse, AggregateRequest, ProcessRequest, DetectRequest,
    RawTripResponse, RawTripListResponse, RawTripDetailResponse,
    DetectEntryExitLLMRequest, LlmVehicleCompareResponse,
)

logger = get_logger(__name__)

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
    end_time: Optional[str] = None,
    # 车辆查询扩展参数
    entry_vehicle_id: Optional[str] = None,
    exit_vehicle_id: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    vehicle_id_match: Optional[str] = None,
    entry_obu_id: Optional[str] = None,
    vehicle_type: Optional[int] = None,
    vehicle_color: Optional[int] = None,
    audit_status: Optional[str] = None,
    min_risk_score: Optional[float] = None,
    max_risk_score: Optional[float] = None,
    min_gantry_count: Optional[int] = None,
    max_gantry_count: Optional[int] = None,
    order_by: Optional[str] = None,
    order: Optional[str] = None,
):
    """获取行程列表（支持任意车辆查询）"""
    # 入参校验
    if vehicle_id_match and vehicle_id_match not in VEHICLE_ID_MATCH_MODES:
        raise HTTPException(status_code=400, detail=f"vehicle_id_match must be one of {VEHICLE_ID_MATCH_MODES}")
    if vehicle_type is not None and vehicle_type not in VEHICLE_TYPE_VALUES:
        raise HTTPException(status_code=400, detail=f"vehicle_type must be one of {VEHICLE_TYPE_VALUES}")
    if min_risk_score is not None and not (0 <= min_risk_score <= 1):
        raise HTTPException(status_code=400, detail="min_risk_score must be in [0, 1]")
    if max_risk_score is not None and not (0 <= max_risk_score <= 1):
        raise HTTPException(status_code=400, detail="max_risk_score must be in [0, 1]")
    if min_risk_score is not None and max_risk_score is not None and min_risk_score > max_risk_score:
        raise HTTPException(status_code=400, detail="min_risk_score must be <= max_risk_score")
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time must be <= end_time")
    if min_gantry_count is not None and max_gantry_count is not None and min_gantry_count > max_gantry_count:
        raise HTTPException(status_code=400, detail="min_gantry_count must be <= max_gantry_count")
    if order_by and order_by not in SORTABLE_COLUMNS:
        raise HTTPException(status_code=400, detail=f"order_by must be one of {sorted(SORTABLE_COLUMNS)}")
    if order and order.lower() not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")

    repo = TripRepository()
    extra = {
        "entry_vehicle_id": entry_vehicle_id,
        "exit_vehicle_id": exit_vehicle_id,
        "vehicle_id": vehicle_id,
        "vehicle_id_match": vehicle_id_match or "exact",
        "entry_obu_id": entry_obu_id,
        "vehicle_type": vehicle_type,
        "vehicle_color": vehicle_color,
        "audit_status": audit_status,
        "min_risk_score": min_risk_score,
        "max_risk_score": max_risk_score,
        "min_gantry_count": min_gantry_count,
        "max_gantry_count": max_gantry_count,
        "order_by": order_by or "entry_time",
        "order": order or "desc",
    }
    trips = repo.get_trips(status=status, limit=limit, offset=offset,
                           entry_station=entry_station, exit_station=exit_station,
                           start_time=start_time, end_time=end_time, **extra)
    total = repo.get_total_count(status=status,
                                 entry_station=entry_station, exit_station=exit_station,
                                 start_time=start_time, end_time=end_time, **extra)
    return TripListResponse(trips=trips, total=total, limit=limit, offset=offset)


@router.get("/trip/{passid}", response_model=TripResponse)
async def get_trip(passid: str):
    """获取行程详情"""
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripResponse(**trip)


@router.get("/trip/{passid}/full", response_model=TripDetailResponse)
async def get_trip_full(passid: str):
    """获取行程完整详情：含门架图片流水 + 关联的稽核结果。"""
    repo = TripRepository()
    trip, results = repo.get_trip_detail_with_results(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # 查询出入口时间范围内的门架抓拍图片流水
    gantry_image_records = None
    entry_vehicle = trip.get('entry_vehicle_id')
    entry_time = trip.get('entry_time')
    exit_time = trip.get('exit_time')
    if entry_vehicle and entry_time and exit_time:
        try:
            images = get_gantry_images_by_vehicle(entry_vehicle, entry_time, exit_time)
            if images:
                gantry_image_records = serialize_gantry_image_records(images)
        except Exception as e:
            logger.error(f"Failed to query gantry images for trip {passid}: {e}")

    result = dict(trip)
    result['gantry_image_records'] = gantry_image_records
    result['audit_results'] = [SuspectResponse(**r) for r in results]
    return TripDetailResponse(**result)


# ---- 车辆查询：Doris 原始数据 ----


@router.get("/doris/vehicles", response_model=RawTripListResponse)
async def list_doris_vehicles(
    vehicle_id: Optional[str] = None,
    vehicle_id_match: Optional[str] = None,
    obu_id: Optional[str] = None,
    vehicle_type: Optional[int] = None,
    vehicle_color: Optional[int] = None,
    entry_station_name: Optional[str] = None,
    exit_station_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    min_gantry_count: Optional[int] = None,
    max_gantry_count: Optional[int] = None,
    order_by: Optional[str] = None,
    order: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """从 Doris 原始表按 PASSID 聚合查询任意车辆通行（不含检测后字段）。"""
    if vehicle_id_match and vehicle_id_match not in VEHICLE_ID_MATCH_MODES_DORIS:
        raise HTTPException(
            status_code=400,
            detail=f"vehicle_id_match must be one of {sorted(VEHICLE_ID_MATCH_MODES_DORIS)}",
        )
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time must be <= end_time")
    if min_gantry_count is not None and max_gantry_count is not None and min_gantry_count > max_gantry_count:
        raise HTTPException(status_code=400, detail="min_gantry_count must be <= max_gantry_count")
    if order_by and order_by not in SORTABLE_COLUMNS_DORIS:
        raise HTTPException(
            status_code=400,
            detail=f"order_by must be one of {sorted(SORTABLE_COLUMNS_DORIS)}",
        )
    if order and order.lower() not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")

    try:
        rows, total = await run_in_threadpool(
            doris_query_trips,
            {
                'vehicle_id': (vehicle_id or '').strip().upper() if vehicle_id else '',
                'vehicle_id_match': vehicle_id_match or 'exact',
                'obu_id': (obu_id or '').strip() if obu_id else None,
                'vehicle_type': vehicle_type,
                'vehicle_color': vehicle_color,
                'entry_station_name': (entry_station_name or '').strip() if entry_station_name else None,
                'exit_station_name': (exit_station_name or '').strip() if exit_station_name else None,
                'start_time': start_time,
                'end_time': end_time,
                'min_gantry_count': min_gantry_count,
                'max_gantry_count': max_gantry_count,
                'order_by': order_by or 'entry_time',
                'order': order or 'desc',
            },
            limit,
            offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("doris_query_trips failed: %s", e)
        raise HTTPException(status_code=500, detail=f"doris query failed: {e}")

    return RawTripListResponse(
        trips=[RawTripResponse(**r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/doris/vehicle/{passid}/full", response_model=RawTripDetailResponse)
async def get_doris_vehicle_full(passid: str):
    """从 Doris 原始数据获取单个行程详情（无 audit_results）。"""
    try:
        detail = await run_in_threadpool(doris_get_trip_detail, passid)
    except Exception as e:
        logger.error("doris_get_trip_detail failed for %s: %s", passid, e)
        raise HTTPException(status_code=500, detail=f"doris query failed: {e}")

    if not detail:
        raise HTTPException(status_code=404, detail="Trip not found")

    return RawTripDetailResponse(**detail)


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
    llm_result: Optional[str] = Query(None, description="same | different | pending"),
    limit: int = 100,
    offset: int = 0
):
    """获取可疑记录列表"""
    repo = AuditRepository()
    suspects = repo.get_suspects(fraud_type=fraud_type, process_status=process_status,
                                 llm_result=llm_result, limit=limit, offset=offset)
    total = repo.get_suspects_count(fraud_type=fraud_type, process_status=process_status,
                                    llm_result=llm_result)
    return SuspectListResponse(suspects=suspects, total=total)


@router.post("/suspect/{suspect_id}/llm-verify", response_model=SuspectResponse)
async def llm_verify_suspect(suspect_id: int):
    """对单条可疑记录手动触发 MaaS 双图比对，写回 verdict 后返回新行。

    错误码：
    - 404：suspect / trip 不存在
    - 400：缺出入口车牌图
    - 502：图片下载失败 / MaaS 不可达 / 响应解析失败
    """
    repo = AuditRepository()
    suspect = repo.get_suspect_detail(suspect_id)
    if not suspect:
        raise HTTPException(status_code=404, detail="Suspect not found")

    passid = suspect.get('passid')
    if not passid:
        raise HTTPException(status_code=400, detail="Suspect has no passid")

    result = await run_in_threadpool(compare_vehicles_by_passid, passid)
    err = result.get('error') if isinstance(result, dict) else None
    if err:
        if err == 'trip_not_found':
            raise HTTPException(status_code=404, detail=result)
        if err == 'image_url_missing':
            raise HTTPException(status_code=400, detail=result)
        raise HTTPException(status_code=502, detail=result)

    from datetime import datetime, timezone
    repo.update_llm_verdict(
        suspect_id,
        is_same=bool(result['is_same_vehicle']),
        confidence=float(result['confidence']),
        reason=str(result.get('reason', '')),
        model=str(result.get('model', '')),
        checked_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    )
    updated = repo.get_suspect_detail(suspect_id)
    return SuspectResponse(**dict(updated or {}))


@router.get("/suspect/{suspect_id}", response_model=SuspectResponse)
async def get_suspect(suspect_id: int):
    """获取可疑记录详情"""
    repo = AuditRepository()
    suspect = repo.get_suspect_detail(suspect_id)
    if not suspect:
        raise HTTPException(status_code=404, detail="Suspect not found")

    # 查询出入口时间范围内的门架抓拍图片流水
    gantry_image_records = None
    entry_vehicle = suspect.get('entry_vehicle_id')
    entry_time = suspect.get('entry_time')
    exit_time = suspect.get('exit_time')
    if entry_vehicle and entry_time and exit_time:
        try:
            images = get_gantry_images_by_vehicle(entry_vehicle, entry_time, exit_time)
            if images:
                gantry_image_records = serialize_gantry_image_records(images)
        except Exception as e:
            logger.error(f"Failed to query gantry images for suspect {suspect_id}: {e}")

    result = dict(suspect)
    result['gantry_image_records'] = gantry_image_records
    return SuspectResponse(**result)


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


@router.post("/detect/entry-exit/llm", response_model=LlmVehicleCompareResponse)
async def detect_entry_exit_with_llm(detect_req: DetectEntryExitLLMRequest):
    """手动调用 MaaS 双图比对出入口车牌特写，判断是否同一辆车。

    错误码：
    - 400：缺 passid 或缺 entry_image_license / exit_image_license
    - 404：trip 在 Doris 中找不到
    - 502：图片下载失败 / MaaS 不可达 / 响应解析失败
    """
    passid = (detect_req.passid or '').strip()
    if not passid:
        raise HTTPException(status_code=400, detail="passid required")

    result = await run_in_threadpool(compare_vehicles_by_passid, passid)

    err = result.get('error')
    if err:
        if err == 'trip_not_found':
            raise HTTPException(status_code=404, detail=result)
        if err == 'image_url_missing':
            raise HTTPException(status_code=400, detail=result)
        # image_download_failed / maas_unavailable / parse_error
        raise HTTPException(status_code=502, detail=result)

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
            trip_id = trip.get('id')
            passid = trip.get('passid')
            
            # 跳过无效数据
            if not trip_id or not passid:
                logger.warning("Skipping invalid trip record: %s", trip)
                continue
                
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
                    repo.save_trip_with_detection_results(trip_id, passid, results_to_save)
                    count += 1
                except Exception as e:
                    logger.error("Failed to save detection results for trip %s: %s", passid, e)
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


# 允许代理的图片来源域名前缀（防止 SSRF）
ALLOWED_IMAGE_PREFIXES = (
    "http://10.",
    "https://10.",
    "http://192.168.",
    "https://192.168.",
    "http://172.",
    "https://172.",
    "http://127.",
    "https://127.",
    "http://localhost",
    "https://localhost",
    "http://10.165.83.43",  # 门架图片服务器
    "https://10.165.83.43",
)


@router.get("/image-proxy")
async def image_proxy(url: str = Query(...)):
    """代理获取内网摄像头图片，避免浏览器跨域/不可达"""
    if not any(url.startswith(p) for p in ALLOWED_IMAGE_PREFIXES):
        raise HTTPException(status_code=400, detail="URL not allowed")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, follow_redirects=True)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Upstream fetch failed")
            content_type = r.headers.get("content-type", "image/jpeg")
            return Response(content=r.content, media_type=content_type, headers={
                "Cache-Control": "public, max-age=300"
            })
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Fetch error: {str(e)}")
