"""稽核系统 API 路由"""

import json
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client
from apps.api.database.repositories.audit_repository import AuditRepository
from apps.api.database.repositories.trip_repository import (
    SORTABLE_COLUMNS,
    VEHICLE_ID_MATCH_MODES,
    VEHICLE_TYPE_VALUES,
    TripRepository,
)
from apps.api.models.schemas import (
    AggregateRequest,
    DetectEntryExitLLMRequest,
    DetectRequest,
    LlmVehicleCompareResponse,
    PassengerObuAnomalyItem,
    PassengerObuAnomalyListResponse,
    PassengerObuDailyStat,
    PassengerObuDailyStatListResponse,
    PassengerObuOverviewResponse,
    ProcessRequest,
    RawTripDetailResponse,
    RawTripListResponse,
    RawTripResponse,
    StatsResponse,
    SuspectListResponse,
    SuspectResponse,
    TripDetailResponse,
    TripListResponse,
    TripResponse,
)
from apps.api.services.doris_trip_query import (
    SORTABLE_COLUMNS_DORIS,
    VEHICLE_ID_MATCH_MODES_DORIS,
)
from apps.api.services.doris_trip_query import (
    get_trip_detail as doris_get_trip_detail,
)
from apps.api.services.doris_trip_query import (
    query_trips as doris_query_trips,
)
from apps.api.services.entry_exit_matcher import EntryExitMatcher
from apps.api.services.trip_aggregator import (
    TripAggregator,
    get_gantry_images_by_vehicle,
    serialize_gantry_image_records,
)
from apps.api.services.vehicle_comparator import compare_vehicles_by_passid

logger = get_logger(__name__)

router = APIRouter()


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
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    entry_station: str | None = None,
    exit_station: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    # 车辆查询扩展参数
    entry_vehicle_id: str | None = None,
    exit_vehicle_id: str | None = None,
    vehicle_id: str | None = None,
    vehicle_id_match: str | None = None,
    entry_obu_id: str | None = None,
    vehicle_type: int | None = None,
    vehicle_color: int | None = None,
    audit_status: str | None = None,
    min_risk_score: float | None = None,
    max_risk_score: float | None = None,
    min_gantry_count: int | None = None,
    max_gantry_count: int | None = None,
    order_by: str | None = None,
    order: str | None = None,
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
    trips = repo.get_trips(
        status=status,
        limit=limit,
        offset=offset,
        entry_station=entry_station,
        exit_station=exit_station,
        start_time=start_time,
        end_time=end_time,
        **extra,
    )
    total = repo.get_total_count(
        status=status,
        entry_station=entry_station,
        exit_station=exit_station,
        start_time=start_time,
        end_time=end_time,
        **extra,
    )
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
    entry_vehicle = trip.get("entry_vehicle_id")
    entry_time = trip.get("entry_time")
    exit_time = trip.get("exit_time")
    if entry_vehicle and entry_time and exit_time:
        try:
            images = get_gantry_images_by_vehicle(entry_vehicle, entry_time, exit_time)
            if images:
                gantry_image_records = serialize_gantry_image_records(images)
        except Exception as e:
            logger.error(f"Failed to query gantry images for trip {passid}: {e}")

    result = dict(trip)
    result["gantry_image_records"] = gantry_image_records
    result["audit_results"] = [SuspectResponse(**r) for r in results]
    return TripDetailResponse(**result)


# ---- 车辆查询：Doris 原始数据 ----


@router.get("/doris/vehicles", response_model=RawTripListResponse)
async def list_doris_vehicles(
    vehicle_id: str | None = None,
    vehicle_id_match: str | None = None,
    obu_id: str | None = None,
    vehicle_type: int | None = None,
    vehicle_color: int | None = None,
    entry_station_name: str | None = None,
    exit_station_name: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    min_gantry_count: int | None = None,
    max_gantry_count: int | None = None,
    order_by: str | None = None,
    order: str | None = None,
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
                "vehicle_id": (vehicle_id or "").strip().upper() if vehicle_id else "",
                "vehicle_id_match": vehicle_id_match or "exact",
                "obu_id": (obu_id or "").strip() if obu_id else None,
                "vehicle_type": vehicle_type,
                "vehicle_color": vehicle_color,
                "entry_station_name": (entry_station_name or "").strip() if entry_station_name else None,
                "exit_station_name": (exit_station_name or "").strip() if exit_station_name else None,
                "start_time": start_time,
                "end_time": end_time,
                "min_gantry_count": min_gantry_count,
                "max_gantry_count": max_gantry_count,
                "order_by": order_by or "entry_time",
                "order": order or "desc",
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
    req.app.state.aggregation_tasks[task_id] = {"status": "running", "current": 0, "total": 0, "count": 0, "passid": ""}

    def run_aggregation():
        aggregator = TripAggregator()
        try:
            total = aggregator.aggregate_recent_trips(
                days=request.days,
                limit=request.limit,
                on_progress=lambda p: req.app.state.aggregation_tasks.update(
                    {
                        task_id: {
                            "status": "running",
                            "current": p["current"],
                            "total": p["total"],
                            "count": p["count"],
                            "passid": p["passid"],
                        }
                    }
                ),
                run_detection=True,
            )
            req.app.state.aggregation_tasks[task_id] = {
                "status": "completed",
                "current": total,
                "total": total,
                "count": total,
                "passid": "",
            }
        except Exception as e:
            req.app.state.aggregation_tasks[task_id] = {"status": "error", "message": str(e)}

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
    fraud_types: list | None = Query(None, description="欺诈类型列表（可重复或逗号分隔）"),
    process_status: str | None = None,
    llm_result: str | None = Query(None, description="same | different | pending"),
    limit: int = 100,
    offset: int = 0,
):
    """获取可疑记录列表"""
    normalized_types: list | None = None
    if fraud_types:
        flat: list = []
        for item in fraud_types:
            if item is None:
                continue
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    flat.append(part)
        if flat:
            normalized_types = flat
    repo = AuditRepository()
    suspects = repo.get_suspects(
        fraud_types=normalized_types, process_status=process_status, llm_result=llm_result, limit=limit, offset=offset
    )
    total = repo.get_suspects_count(fraud_types=normalized_types, process_status=process_status, llm_result=llm_result)
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

    passid = suspect.get("passid")
    if not passid:
        raise HTTPException(status_code=400, detail="Suspect has no passid")

    result = await run_in_threadpool(compare_vehicles_by_passid, passid)
    err = result.get("error") if isinstance(result, dict) else None
    if err:
        if err == "trip_not_found":
            raise HTTPException(status_code=404, detail=result)
        if err == "image_url_missing":
            raise HTTPException(status_code=400, detail=result)
        raise HTTPException(status_code=502, detail=result)

    from datetime import datetime, timezone

    repo.update_llm_verdict(
        suspect_id,
        is_same=bool(result["is_same_vehicle"]),
        confidence=float(result["confidence"]),
        reason=str(result.get("reason", "")),
        model=str(result.get("model", "")),
        checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    entry_vehicle = suspect.get("entry_vehicle_id")
    entry_time = suspect.get("entry_time")
    exit_time = suspect.get("exit_time")
    if entry_vehicle and entry_time and exit_time:
        try:
            images = get_gantry_images_by_vehicle(entry_vehicle, entry_time, exit_time)
            if images:
                gantry_image_records = serialize_gantry_image_records(images)
        except Exception as e:
            logger.error(f"Failed to query gantry images for suspect {suspect_id}: {e}")

    result = dict(suspect)
    result["gantry_image_records"] = gantry_image_records
    return SuspectResponse(**result)


@router.post("/suspect/{suspect_id}/process")
async def process_suspect(suspect_id: int, request: ProcessRequest):
    """处理可疑记录"""
    repo = AuditRepository()
    repo.update_process_status(suspect_id, request.action, request.operator, request.comments)
    return {"message": "Processed successfully"}


@router.post("/detect/passenger-obu")
async def detect_passenger_obu(detect_req: DetectRequest):
    """检测客车套用货车 OBU（入口或出口图片识别为货车 + LLM 复核通过）"""
    passid = detect_req.passid
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    from apps.api.services.passenger_obu_detector import FRAUD_TYPE, detect_trip

    details = detect_trip(trip)
    if not details:
        return {"is_suspicious": False, "fraud_type": FRAUD_TYPE, "details": None}

    audit_repo = AuditRepository()
    audit_repo.save_result(
        {
            "audit_trip_id": trip["id"],
            "fraud_type": FRAUD_TYPE,
            "entry_vehicle_type": details.get("entry_vehicle_type"),
            "exit_vehicle_type": details.get("exit_vehicle_type"),
            "is_suspicious": 1,
            "risk_score": details.get("risk_score", 0.85),
            "details": json.dumps(
                {
                    "source_side": details.get("source_side"),
                    "entry_obu_id": details.get("entry_obu_id"),
                    "exit_obu_id": details.get("exit_obu_id"),
                    "entry_media_type": details.get("entry_media_type"),
                    "exit_media_type": details.get("exit_media_type"),
                    "entry_visual_type": details.get("entry_visual_type"),
                    "exit_visual_type": details.get("exit_visual_type"),
                    "visual_vehicle_type": details.get("visual_vehicle_type"),
                    "llm_verified": details.get("llm_verified"),
                    "llm_confidence": details.get("llm_confidence"),
                    "llm_call_status": details.get("llm_call_status"),
                    "entry_image_trans": details.get("entry_image_trans"),
                    "exit_image_trans": details.get("exit_image_trans"),
                    "rule_version": "v1",
                },
                ensure_ascii=False,
            ),
        }
    )

    return {
        "is_suspicious": True,
        "fraud_type": FRAUD_TYPE,
        "details": details,
    }


@router.post("/detect/entry-exit")
async def detect_entry_exit(detect_req: DetectRequest, request: Request):
    """检测出入口车辆不一致"""
    passid = detect_req.passid
    repo = TripRepository()
    trip = repo.get_trip_detail(passid)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    matcher = get_entry_exit_matcher(request)
    entry_record = {"image_license": trip.get("entry_image_license")}
    exit_record = {"image_license": trip.get("exit_image_license")}
    result = matcher.compare(entry_record, exit_record)

    if result.get("is_suspicious"):
        audit_repo = AuditRepository()
        audit_repo.save_result(
            {
                "audit_trip_id": trip["id"],
                "fraud_type": "ENTRY_EXIT_MISMATCH",
                "entry_visual_type": result.get("entry_visual_type"),
                "exit_visual_type": result.get("exit_visual_type"),
                "entry_color": result.get("entry_color"),
                "exit_color": result.get("exit_color"),
                "is_suspicious": 1,
                "risk_score": result.get("fingerprint_sim", 0),
                "details": json.dumps(result),
            }
        )

    return result


@router.post("/detect/entry-exit/llm", response_model=LlmVehicleCompareResponse)
async def detect_entry_exit_with_llm(detect_req: DetectEntryExitLLMRequest):
    """手动调用 MaaS 双图比对出入口车牌特写，判断是否同一辆车。

    错误码：
    - 400：缺 passid 或缺 entry_image_license / exit_image_license
    - 404：trip 在 Doris 中找不到
    - 502：图片下载失败 / MaaS 不可达 / 响应解析失败
    """
    passid = (detect_req.passid or "").strip()
    if not passid:
        raise HTTPException(status_code=400, detail="passid required")

    result = await run_in_threadpool(compare_vehicles_by_passid, passid)

    err = result.get("error")
    if err:
        if err == "trip_not_found":
            raise HTTPException(status_code=404, detail=result)
        if err == "image_url_missing":
            raise HTTPException(status_code=400, detail=result)
        # image_download_failed / maas_unavailable / parse_error
        raise HTTPException(status_code=502, detail=result)

    return result


@router.post("/detect/recognize-plate")
async def recognize_plate(image_url: str = Query(..., description="车牌图片 URL")):
    """调公共服务 OCR 识别车牌号。

    错误码：
    - 400：缺 image_url
    - 502：公共服务不可达 / 响应解析失败
    """
    if not image_url.strip():
        raise HTTPException(status_code=400, detail="image_url required")

    result = await run_in_threadpool(get_client().recognize_plate, image_url)

    if isinstance(result, dict) and "error" in result:
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
        "passid": "",
    }

    def run_re_detect():
        repo = TripRepository()
        trips = repo.get_trips_without_visual(limit=500)
        total = len(trips)
        count = 0

        for i, trip in enumerate(trips):
            trip_id = trip.get("id")
            passid = trip.get("passid")

            # 跳过无效数据
            if not trip_id or not passid:
                logger.warning("Skipping invalid trip record: %s", trip)
                continue

            results_to_save = []

            if trip.get("entry_image_license") and trip.get("exit_image_license"):
                try:
                    matcher = get_entry_exit_matcher(request)
                    entry_rec = {"image_license": trip.get("entry_image_license")}
                    exit_rec = {"image_license": trip.get("exit_image_license")}
                    r = matcher.compare(entry_rec, exit_rec)
                    if r.get("_comparison_success") or r.get("fingerprint_sim"):
                        results_to_save.append(
                            {
                                "audit_trip_id": trip_id,
                                "fraud_type": "ENTRY_EXIT_MISMATCH",
                                "entry_visual_type": r.get("entry_visual_type"),
                                "exit_visual_type": r.get("exit_visual_type"),
                                "entry_color": r.get("entry_color"),
                                "exit_color": r.get("exit_color"),
                                "is_suspicious": 1 if r.get("is_suspicious") else 0,
                                "risk_score": r.get("fingerprint_sim", 0),
                                "details": json.dumps(r),
                            }
                        )
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
                "passid": trip["passid"],
            }

        request.app.state.aggregation_tasks[task_id] = {
            "status": "completed",
            "current": total,
            "total": total,
            "count": count,
            "passid": "",
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
            return Response(
                content=r.content, media_type=content_type, headers={"Cache-Control": "public, max-age=300"}
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Fetch error: {e!s}")


# ---- 客车 OBU 监测（PASSENGER_USES_TRUCK_OBU_NON_NEW_A）----


@router.get("/passenger-obu/overview", response_model=PassengerObuOverviewResponse)
async def get_passenger_obu_overview():
    """顶部卡片：累计扫描 / 异常 / 待处理 / 已确认 + 最近 30 天趋势"""
    from datetime import date, timedelta

    from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository

    stats_repo = TruckObuStatsRepository()
    overview = stats_repo.get_overview()
    pending = AuditRepository().get_suspects_count(
        fraud_type="PASSENGER_USES_TRUCK_OBU_NON_NEW_A",
        process_status="UNPROCESSED",
    )
    overview["total_pending"] = pending
    overview["last_30_days"] = stats_repo.get_daily_stats(
        from_date=(date.today() - timedelta(days=29)).isoformat(),
        to_date=date.today().isoformat(),
        fraud_type="PASSENGER_USES_TRUCK_OBU_NON_NEW_A",
    )
    return PassengerObuOverviewResponse(**overview)


@router.get("/passenger-obu/stats/daily", response_model=PassengerObuDailyStatListResponse)
async def get_passenger_obu_daily_stats(
    from_date: str | None = Query(None, description="YYYY-MM-DD"),
    to_date: str | None = Query(None, description="YYYY-MM-DD"),
    fraud_type: str | None = Query(None, description="默认只取 PASSENGER_USES_TRUCK_OBU_NON_NEW_A"),
):
    """每日统计（按 fraud_type 聚合）"""
    from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository

    stats_repo = TruckObuStatsRepository()
    if fraud_type is None:
        fraud_type = "PASSENGER_USES_TRUCK_OBU_NON_NEW_A"
    stats = stats_repo.get_daily_stats(from_date=from_date, to_date=to_date, fraud_type=fraud_type)
    items = [
        PassengerObuDailyStat(
            date=r["date"],
            fraud_type=r["fraud_type"],
            scanned_count=r["scanned_count"],
            suspicious_count=r["suspicious_count"],
            confirmed_count=r["confirmed_count"],
            last_run_at=r.get("last_run_at"),
        )
        for r in stats
    ]
    return PassengerObuDailyStatListResponse(stats=items, total=len(items))


@router.get("/passenger-obu/anomalies", response_model=PassengerObuAnomalyListResponse)
async def get_passenger_obu_anomalies(
    process_status: str | None = None,
    llm_result: str | None = None,
    sort_by: str = Query("exit_time", description="排序字段:exit_time / created_at / risk_score"),
    limit: int = 50,
    offset: int = 0,
):
    """异常记录列表（复用 AuditRepository.get_suspects，仅过滤 fraud_types）

    sort_by 默认 exit_time DESC,白名单限定防止 SQL 注入。
    """
    audit_repo = AuditRepository()
    rows = audit_repo.get_suspects(
        fraud_types=["PASSENGER_USES_TRUCK_OBU_NON_NEW_A"],
        process_status=process_status,
        llm_result=llm_result,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    total = audit_repo.get_suspects_count(
        fraud_types=["PASSENGER_USES_TRUCK_OBU_NON_NEW_A"],
        process_status=process_status,
        llm_result=llm_result,
    )
    items: list[PassengerObuAnomalyItem] = []
    for r in rows:
        source_side = None
        entry_obu_id = None
        exit_obu_id = None
        entry_media_type = None
        exit_media_type = None
        visual_vehicle_type = None
        llm_verified = None
        llm_confidence = None
        llm_call_status = None
        entry_image_trans = None
        exit_image_trans = None
        if r.get("details"):
            try:
                d = json.loads(r["details"]) if isinstance(r["details"], str) else r["details"]
                source_side = d.get("source_side")
                entry_obu_id = d.get("entry_obu_id")
                exit_obu_id = d.get("exit_obu_id")
                entry_media_type = d.get("entry_media_type")
                exit_media_type = d.get("exit_media_type")
                visual_vehicle_type = d.get("visual_vehicle_type")
                llm_verified = d.get("llm_verified")
                llm_confidence = d.get("llm_confidence")
                llm_call_status = d.get("llm_call_status")
                entry_image_trans = d.get("entry_image_trans")
                exit_image_trans = d.get("exit_image_trans")
            except Exception:
                pass
        items.append(
            PassengerObuAnomalyItem(
                id=r["id"],
                audit_trip_id=r["audit_trip_id"],
                fraud_type=r["fraud_type"],
                passid=r.get("passid"),
                entry_time=r.get("entry_time"),
                exit_time=r.get("exit_time"),
                entry_station_name=r.get("entry_station_name"),
                exit_station_name=r.get("exit_station_name"),
                entry_vehicle_id=r.get("entry_vehicle_id"),
                exit_vehicle_id=r.get("exit_vehicle_id"),
                entry_vehicle_type=r.get("entry_vehicle_type"),
                exit_vehicle_type=r.get("exit_vehicle_type"),
                entry_obu_id=entry_obu_id,
                exit_obu_id=exit_obu_id,
                entry_media_type=entry_media_type,
                exit_media_type=exit_media_type,
                risk_score=r.get("risk_score", 0.85),
                process_status=r.get("process_status", "UNPROCESSED"),
                details=r.get("details"),
                source_side=source_side,
                visual_vehicle_type=visual_vehicle_type,
                llm_verified=llm_verified,
                llm_confidence=llm_confidence,
                llm_call_status=llm_call_status,
                entry_image_trans=entry_image_trans,
                exit_image_trans=exit_image_trans,
                created_at=r.get("created_at"),
            )
        )
    return PassengerObuAnomalyListResponse(anomalies=items, total=total, limit=limit, offset=offset)
