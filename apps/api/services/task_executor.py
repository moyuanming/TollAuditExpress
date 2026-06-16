"""任务执行器 — 根据任务配置执行聚合+检测"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import local
from typing import Dict, List

logger = logging.getLogger(__name__)

# 容器是 UTC，DB 走北京时间 — 与各 repository 一致
_BEIJING_TZ = timezone(timedelta(hours=8))

# 当前线程正在执行的 execution_id（由调度器在启动执行线程时设置）
_ctx = local()

# 各 execution 的日志缓冲 — 必须跨线程共享,否则 flusher 线程读不到执行线程的日志
_log_buffers: Dict[int, List[str]] = {}


def set_log_context(execution_id: int):
    """在执行线程启动时调用,把当前 execution_id 写入 thread-local,初始化缓冲"""
    _ctx.execution_id = execution_id
    _log_buffers[execution_id] = []


def clear_log_context(execution_id: int):
    """在执行线程退出时调用,清掉 thread-local 标记和缓冲"""
    if getattr(_ctx, 'execution_id', None) == execution_id:
        _ctx.execution_id = None
    _log_buffers.pop(execution_id, None)


def get_log_lines(execution_id: int) -> list[str]:
    """返回指定 execution 的缓冲(供调度器 flush 到 DB)"""
    return _log_buffers.get(execution_id, [])


class _CaptureHandler(logging.Handler):
    """把日志记录追加到当前线程对应 execution 的缓冲里"""

    def emit(self, record: logging.LogRecord):
        eid = getattr(_ctx, 'execution_id', None)
        if eid is None:
            return
        lines = _log_buffers.get(eid)
        if lines is None:
            return
        try:
            lines.append(self.format(record))
        except Exception:
            pass


def execute_task(task: dict) -> dict:
    """执行单个任务，返回结果摘要"""
    task_type = task.get('task_type', 'aggregate_detect')
    filter_rules = {}
    if task.get('filter_rules'):
        try:
            filter_rules = json.loads(task['filter_rules'])
        except (json.JSONDecodeError, TypeError):
            pass

    from apps.api.database.repositories.trip_repository import TripRepository
    trip_repo = TripRepository()

    if task_type == 'aggregate_detect':
        return _execute_aggregate_detect(filter_rules, trip_repo)
    elif task_type == 'detect_only':
        return _execute_detect_only(filter_rules, trip_repo)
    elif task_type == 'multi_detect':
        return _execute_multi_detect(filter_rules, trip_repo)
    elif task_type == 're_detect':
        return _execute_re_detect(trip_repo)
    elif task_type == 'passenger_obu_audit':
        return _execute_passenger_obu_audit(filter_rules, task, trip_repo)
    elif task_type == 'llm_verify':
        return _execute_llm_verify(filter_rules)
    else:
        return {"error": f"Unknown task_type: {task_type}"}


def _execute_llm_verify(filter_rules: dict) -> dict:
    """AI 二次复核：批跑所有 llm_checked_at IS NULL 的可疑记录（走 vehicle-ai-service）。"""
    from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects
    limit = int(filter_rules.get('limit', 50))
    max_workers = int(filter_rules.get('max_workers', 4))
    return run_ai_verify_batch_for_suspects(limit=limit, max_workers=max_workers)


def _execute_aggregate_detect(filter_rules: dict, trip_repo) -> dict:
    """聚合+检测"""
    days = filter_rules.get('days', 3)
    limit = filter_rules.get('limit', 500)
    exit_station = filter_rules.get('exit_station', '')
    entry_station = filter_rules.get('entry_station', '')

    aggregator = None
    from apps.api.services.trip_aggregator import TripAggregator
    aggregator = TripAggregator()

    if exit_station or entry_station:
        return _targeted_aggregate(exit_station, entry_station, days, limit, trip_repo, aggregator)

    aggregated = aggregator.aggregate_recent_trips(days=days, limit=limit, run_detection=True)
    stats = trip_repo.get_stats()
    return {"aggregated": aggregated, "detected": 0, "suspected": stats.get('suspected_trips', 0)}


def _targeted_aggregate(exit_station: str, entry_station: str, days: int, limit: int, trip_repo, aggregator) -> dict:
    """定向聚合指定站点"""
    import pymysql
    from apps.api.services.trip_aggregator import DB_CONFIG, aggregate_trip

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    conditions = ["t.LANETYPE = '出口'", "t.MEDIATYPE = 1",
                  "t.OCCURTIME >= DATE_SUB(NOW(), INTERVAL %s DAY)"]
    params = [days]
    if exit_station:
        conditions.append("t.STATION_NAME LIKE %s")
        params.append(f"%{exit_station}%")

    sql = f"""
    SELECT t.PASSID FROM dwd_tolldata.t_waste_en_ex_gantry t
    WHERE {' AND '.join(conditions)}
    GROUP BY t.PASSID ORDER BY MAX(t.OCCURTIME) DESC LIMIT %s
    """
    params.append(limit)
    cursor.execute(sql, params)
    passids = [r['PASSID'] for r in cursor.fetchall()]
    cursor.close()
    conn.close()

    logger.info("Targeted aggregate: %d PASSIDs found", len(passids))

    aggregated = 0
    for passid in passids:
        existing = trip_repo.get_trip_detail(passid)
        if existing:
            continue
        trip_data = aggregate_trip(passid)
        if not trip_data:
            continue
        trip_id = trip_repo.save_trip(trip_data)
        if trip_id:
            aggregated += 1
            try:
                aggregator._run_detection(trip_data, trip_id)
            except Exception as e:
                logger.warning("Detection failed for %s: %s", passid, e)

    stats = trip_repo.get_stats()
    return {"aggregated": aggregated, "detected": aggregated, "suspected": stats.get('suspected_trips', 0)}


def _execute_detect_only(filter_rules: dict, trip_repo) -> dict:
    """仅检测 (entry-exit 比对)。客车 OBU 套用检测由 passenger_obu_audit 任务独立负责。"""
    exit_station = filter_rules.get('exit_station', '')
    entry_station = filter_rules.get('entry_station', '')
    limit = filter_rules.get('limit', 200)

    from apps.api.services.entry_exit_matcher import EntryExitMatcher

    trips = trip_repo.get_trips_without_visual(limit=limit)
    matcher = EntryExitMatcher()
    detected = 0
    suspected = 0

    for trip in trips:
        passid = trip['passid']
        trip_id = trip['id']

        if exit_station and exit_station not in (trip.get('exit_station_name') or ''):
            continue
        if entry_station and entry_station not in (trip.get('entry_station_name') or ''):
            continue

        trip_results = []
        try:
            r = matcher.compare(
                {'image_license': trip.get('entry_image_license')},
                {'image_license': trip.get('exit_image_license')}
            )
            if r.get('_comparison_success') or r.get('fingerprint_sim'):
                trip_results.append({
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
        except Exception as e:
            logger.debug("Model B error: %s", e)

        if trip_results:
            try:
                trip_repo.save_trip_with_detection_results(trip_id, passid, trip_results)
                detected += 1
                if any(r['is_suspicious'] for r in trip_results):
                    suspected += 1
            except Exception as e:
                logger.error("Save error for %s: %s", passid, e)

    return {"aggregated": 0, "detected": detected, "suspected": suspected}


def _execute_re_detect(trip_repo) -> dict:
    """补检测 (entry-exit 比对)。客车 OBU 套用检测由 passenger_obu_audit 任务独立负责。"""
    from apps.api.services.entry_exit_matcher import EntryExitMatcher

    trips = trip_repo.get_trips_without_visual(limit=500)
    matcher = EntryExitMatcher()
    detected = 0
    suspected = 0

    for trip in trips:
        trip_id = trip['id']
        passid = trip['passid']
        trip_results = []

        if trip.get('entry_image_license') and trip.get('exit_image_license'):
            try:
                r = matcher.compare(
                    {'image_license': trip.get('entry_image_license')},
                    {'image_license': trip.get('exit_image_license')}
                )
                if r.get('_comparison_success') or r.get('fingerprint_sim'):
                    trip_results.append({
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

        if trip_results:
            try:
                trip_repo.save_trip_with_detection_results(trip_id, passid, trip_results)
                detected += 1
                if any(r['is_suspicious'] for r in trip_results):
                    suspected += 1
            except Exception:
                pass

    return {"aggregated": 0, "detected": detected, "suspected": suspected}


def _execute_multi_detect(filter_rules: dict, trip_repo) -> dict:
    """多维度检测：RuleEngine + 内置 Detector 联合执行"""
    from apps.api.services.rule_engine import RuleEngine
    from apps.api.services.rule_loader import load_rules
    from apps.api.services.detectors import all_detectors

    # filter_rules 可能被双层 JSON 编码，确保是 dict
    if isinstance(filter_rules, str):
        try:
            filter_rules = json.loads(filter_rules)
        except (json.JSONDecodeError, TypeError):
            filter_rules = {}
    if not isinstance(filter_rules, dict):
        filter_rules = {}

    limit = int(filter_rules.get('limit', 200))
    fraud_types = filter_rules.get('fraud_types')

    engine = RuleEngine()
    try:
        rules = load_rules()
        engine.load_from_dicts(rules)
    except Exception as e:
        logger.warning("Failed to load rules, running detectors only: %s", e)

    trips = trip_repo.get_trips(limit=limit)
    detected = 0
    suspected = 0

    for trip in trips:
        trip_id = trip['id']
        passid = trip['passid']
        trip_results = []

        rule_results = engine.run(trip, fraud_types=fraud_types)
        for rr in rule_results:
            trip_results.append({
                'audit_trip_id': trip_id,
                'fraud_type': rr['fraud_type'],
                'is_suspicious': rr['is_suspicious'],
                'risk_score': rr['risk_score'],
                'rule_id': rr.get('rule_id'),
                'dry_run': rr.get('dry_run', 0),
                'details': json.dumps(rr.get('details', {}), ensure_ascii=False),
            })

        for det in all_detectors():
            if fraud_types and det.fraud_type not in fraud_types:
                continue
            try:
                r = det.detect(trip)
                if r:
                    trip_results.append({
                        'audit_trip_id': trip_id,
                        'fraud_type': r['fraud_type'],
                        'is_suspicious': 1 if r.get('risk_hint', 0) >= 0.6 else 0,
                        'risk_score': r.get('risk_hint', 0),
                        'details': json.dumps(r, ensure_ascii=False),
                    })
            except Exception as e:
                logger.debug("Detector %s error: %s", det.fraud_type, e)

        if trip_results:
            try:
                trip_repo.save_trip_with_detection_results(trip_id, passid, trip_results)
                detected += 1
                if any(r['is_suspicious'] for r in trip_results):
                    suspected += 1
            except Exception as e:
                logger.error("Save error for %s: %s", passid, e)

    return {"multi_detect": True, "detected": detected, "suspected": suspected}


# ---- 客车 OBU 监测（task_type='passenger_obu_audit'）----


def _execute_passenger_obu_audit(filter_rules: dict, task: dict, trip_repo) -> dict:
    """客车申报 + 非新A + 图片识别为货车 + LLM 复核通过 → 命中。

    调度语义:
      - 首次执行（last_run_at 为空）→ 扫描窗口 [start_time, NOW]
      - 增量执行 → 扫描窗口 [last_run_at - 5min, NOW]（重叠容错防漏边界）

    返回 dict 含:
      - scanned: 候选 trip 总数
      - suspicious: 命中并写入 audit_results 的条数
      - window_start / window_end: 实际扫描窗口
      - anomaly_count / anomaly_ids_sample: 命中的 audit_results.id 列表（前 50 个）
    """
    from apps.api.services.passenger_obu_detector import detect_trip, FRAUD_TYPE
    from apps.api.services.doris_trip_query import find_passenger_obu_candidates_doris
    from apps.api.database.repositories.audit_repository import AuditRepository
    from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository

    rules = _normalize_passenger_obu_rules(filter_rules or {})
    audit_repo = AuditRepository()
    stats_repo = TruckObuStatsRepository()

    last_run_at = task.get('last_run_at')
    if last_run_at:
        start_dt = _parse_dt(last_run_at) - timedelta(minutes=5)
    else:
        start_dt = _parse_dt(rules['start_time'])
    end_dt = datetime.now(_BEIJING_TZ).replace(tzinfo=None)
    logger.info("Passenger OBU audit window: %s ~ %s (workers=%d)",
                start_dt, end_dt, rules['max_workers'])

    scanned = 0
    suspicious = 0
    new_anomaly_ids: List[int] = []
    # 按 trip 的实际 entry_time 所在日期累加,避免跨天扫描被错归到起始日。
    per_day_scanned: Dict[str, int] = {}
    per_day_suspicious: Dict[str, int] = {}
    last_run_at_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    def _flush_daily_stats() -> None:
        """把当前 per-day 累加器落库。每页调一次,被 60 分钟硬限 kill 时
        最多丢失当前正在处理的一页(page_size 默认 500),不再丢整批。"""
        for day, c in per_day_scanned.items():
            stats_repo.upsert_daily_stat(
                date=day,
                fraud_type=FRAUD_TYPE,
                scanned_count_delta=c,
                suspicious_count_delta=per_day_suspicious.get(day, 0),
                last_run_at=last_run_at_str,
            )

    def _detect_one(trip: dict):
        """对单条 trip 跑 detect_trip,异常吞掉返回 None(原 for 循环本来就 try)."""
        try:
            return trip, detect_trip(trip)
        except Exception as e:
            logger.warning("detect_trip failed for passid=%s: %s",
                           trip.get('passid'), e)
            return trip, None

    offset = 0
    while scanned < rules['limit']:
        rows = find_passenger_obu_candidates_doris(
            start_time=start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            end_time=end_dt.strftime('%Y-%m-%d %H:%M:%S'),
            plate_prefix_exclude=rules['plate_prefix_exclude'],
            declared_vehicle_type=rules['declared_vehicle_type'],
            media_type=1,
            limit=rules['page_size'],
            offset=offset,
        )
        if not rows:
            break
        scanned += len(rows)

        # 并行调 AI service。detect_trip 内部会调 1-2 次(每侧一次),
        # 单 trip 的多侧仍是串行(共享 trip 上下文),但 trip 之间并行。
        # max_workers 默认 4 — 经验值:AI service GPU 队列不会拥堵,
        # 4 路并发可把 ~10 trips/min 提到 ~30+ trips/min。
        with ThreadPoolExecutor(max_workers=rules['max_workers']) as ex:
            for trip, details in ex.map(_detect_one, rows):
                # 按 entry_time 落桶;entry_time 缺失时落到 exit_time,都没有则归 end_dt
                t_for_day = _parse_dt(trip.get('entry_time')) or _parse_dt(trip.get('exit_time')) or end_dt
                day_key = t_for_day.strftime('%Y-%m-%d')
                per_day_scanned[day_key] = per_day_scanned.get(day_key, 0) + 1

                if details is None:
                    continue
                try:
                    # 确保 audit_trips 有记录（Doris 原始数据无 id，需 upsert 拿 FK）
                    trip_id = trip_repo.save_trip(trip)
                    rid = audit_repo.save_result({
                        'audit_trip_id': trip_id,
                        'fraud_type': FRAUD_TYPE,
                        'entry_vehicle_type': details['entry_vehicle_type'],
                        'exit_vehicle_type': details['exit_vehicle_type'],
                        'is_suspicious': 1,
                        'risk_score': details['risk_score'],
                        'details': json.dumps({
                            'source_side': details['source_side'],
                            'entry_obu_id': details['entry_obu_id'],
                            'exit_obu_id': details['exit_obu_id'],
                            'entry_media_type': details.get('entry_media_type'),
                            'exit_media_type': details.get('exit_media_type'),
                            'entry_visual_type': details['entry_visual_type'],
                            'exit_visual_type': details['exit_visual_type'],
                            'visual_vehicle_type': details['visual_vehicle_type'],
                            'llm_verified': details['llm_verified'],
                            'llm_confidence': details['llm_confidence'],
                            'llm_reason': details.get('llm_reason'),
                            'rule_version': 'v1',
                        }, ensure_ascii=False),
                    })
                    new_anomaly_ids.append(rid)
                    suspicious += 1
                    per_day_suspicious[day_key] = per_day_suspicious.get(day_key, 0) + 1
                except Exception as e:
                    logger.warning(
                        "save audit_result failed for passid=%s: %s",
                        trip.get('passid'), e,
                    )
        # 每页 flush:即使 60 分钟硬限 kill,已完成的页面数据已落库
        _flush_daily_stats()
        if len(rows) < rules['page_size']:
            break
        offset += rules['page_size']

    return {
        'task_type': 'passenger_obu_audit',
        'window_start': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'window_end': end_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'scanned': scanned,
        'suspicious': suspicious,
        'anomaly_count': len(new_anomaly_ids),
        'anomaly_ids_sample': new_anomaly_ids[:50],
    }


def _normalize_passenger_obu_rules(filter_rules: dict) -> dict:
    return {
        'start_time': filter_rules.get('start_time', '2026-06-01 00:00:00'),
        'declared_vehicle_type': int(filter_rules.get('declared_vehicle_type', 1)),
        'plate_prefix_exclude': filter_rules.get('plate_prefix_exclude', '新A'),
        'limit': int(filter_rules.get('limit', 2000)),
        'page_size': int(filter_rules.get('page_size', 500)),
        'max_workers': int(filter_rules.get('max_workers', 4)),
    }


def _parse_dt(s) -> datetime:
    if isinstance(s, datetime):
        return s
    if not s:
        return datetime.now()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now()
