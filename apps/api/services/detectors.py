"""多维度检测器 — 阶段 1 MVP

4 个新 fraud_type 检测器：
  - GATEWAY_ANOMALY:        门架跳点 / U-J 型
  - VEHICLE_TYPE_DOWNGRADE: 大车小标（视觉 vs 申报）
  - SAME_PLATE_DIFF_VEHICLE: 同牌不同车
  - OBU_UNBIND:             OBU 借用 / 倒卖
  - OBU_SHIELD:             OBU 屏蔽

接口：
  BaseDetector.fraud_type -> str
  BaseDetector.detect(trip) -> Optional[dict]   # 返回 details，None 表示未命中
  BaseDetector.batch_detect(trips) -> List[Optional[dict]]

trip 字典字段约定（与 trip_aggregator.serialize_gantry_records 一致）：
  entry_vehicle_id, entry_vehicle_type, entry_obu_id, entry_image_license, entry_image_trans
  exit_vehicle_id,  exit_vehicle_type,  exit_obu_id,  exit_image_license,  exit_image_trans
  gantry_count: int
  gantry_records: JSON 字符串或 list[dict]，每个含 station_id / occur_time / vehicle_type / obu_id
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from apps.api.core.vehicle_ai_client import get_client

VEHICLE_TYPE_PASSENGER = 1
VEHICLE_TYPE_TRUCK_LIGHT = 2
VEHICLE_TYPE_TRUCK_MEDIUM = 3
VEHICLE_TYPE_TRUCK_HEAVY = 4
VEHICLE_TYPE_TRUCK_SPECIAL = 5
TRUCK_TYPES = frozenset(
    [VEHICLE_TYPE_TRUCK_LIGHT, VEHICLE_TYPE_TRUCK_MEDIUM, VEHICLE_TYPE_TRUCK_HEAVY, VEHICLE_TYPE_TRUCK_SPECIAL]
)


class BaseDetector(Protocol):
    fraud_type: str

    def detect(self, trip: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...

    def batch_detect(self, trips: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        return [self.detect(t) for t in trips]


def parse_gantry_records(gantry_records: Any) -> List[Dict[str, Any]]:
    if not gantry_records:
        return []
    if isinstance(gantry_records, str):
        import json
        try:
            return json.loads(gantry_records)
        except (ValueError, TypeError):
            return []
    if isinstance(gantry_records, list):
        return gantry_records
    return []


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ============================================================
# GatewayDetector
# ============================================================


class GatewayDetector:
    fraud_type = "GATEWAY_ANOMALY"

    def __init__(self, topology: Optional[List[Dict[str, Any]]] = None):
        self._connected: set = set()
        self._distances: Dict[tuple, float] = {}
        for edge in topology or []:
            if int(edge.get("is_connected", 1) or 1) == 1:
                a, b = edge.get("from_station"), edge.get("to_station")
                self._connected.add((a, b))
                if edge.get("distance_km") is not None:
                    self._distances[(a, b)] = float(edge["distance_km"])

    def detect(self, trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        records = parse_gantry_records(trip.get("gantry_records"))
        if len(records) < 2:
            return None

        skip_stations: List[Dict[str, Any]] = []
        loop_detected = False
        seen_stations: set = set()

        for i, r in enumerate(records):
            sid = r.get("station_id")
            if sid is None:
                continue
            if sid in seen_stations:
                loop_detected = True
            seen_stations.add(sid)

        for i in range(len(records) - 1):
            a = records[i].get("station_id")
            b = records[i + 1].get("station_id")
            if a is None or b is None:
                continue
            if a == b:
                continue  # handled by seen_stations above
            if self._connected and (a, b) not in self._connected:
                skip_stations.append({"from": a, "to": b, "index": i})

        speed_avg = _compute_avg_speed_kmh(records, self._distances)
        speed_anomaly = speed_avg is not None and (speed_avg < 10 or speed_avg > 200)

        if not skip_stations and not loop_detected and not speed_anomaly:
            return None

        return {
            "fraud_type": self.fraud_type,
            "skip_stations": skip_stations,
            "loop_detected": loop_detected,
            "speed_avg_kmh": speed_avg,
            "gantry_count": len(records),
            "risk_hint": min(1.0, 0.6 + 0.1 * min(len(skip_stations), 3) + (0.2 if loop_detected else 0.0)),
        }


def _compute_avg_speed_kmh(
    records: List[Dict[str, Any]], distances: Dict[tuple, float]
) -> Optional[float]:
    if len(records) < 2:
        return None
    total_km = 0.0
    total_min = 0.0
    for i in range(len(records) - 1):
        t_a = _parse_time(records[i].get("occur_time"))
        t_b = _parse_time(records[i + 1].get("occur_time"))
        if t_a is None or t_b is None:
            continue
        delta_min = (t_b - t_a).total_seconds() / 60.0
        if delta_min <= 0:
            continue
        total_min += delta_min
        a = records[i].get("station_id")
        b = records[i + 1].get("station_id")
        if (a, b) in distances:
            total_km += distances[(a, b)]
    if total_min <= 0 or total_km <= 0:
        return None
    return round(total_km / (total_min / 60.0), 1)


# ============================================================
# VehicleTypeDetector
# ============================================================


class VehicleTypeDetector:
    fraud_type = "VEHICLE_TYPE_DOWNGRADE"

    def __init__(self, ai_client: Any = None):
        self._client = ai_client

    def detect(self, trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entry_declared = trip.get("entry_vehicle_type")
        exit_declared = trip.get("exit_vehicle_type")
        entry_image = trip.get("entry_image_license") or trip.get("entry_image_trans")
        exit_image = trip.get("exit_image_license") or trip.get("exit_image_trans")

        if not entry_image and not exit_image:
            return None

        visual_entry = self._classify(entry_image) if entry_image else None
        visual_exit = self._classify(exit_image) if exit_image else None

        downgrade_entry = _is_downgrade(visual_entry, entry_declared)
        downgrade_exit = _is_downgrade(visual_exit, exit_declared)

        if not downgrade_entry and not downgrade_exit:
            return None

        return {
            "fraud_type": self.fraud_type,
            "visual_entry_type": visual_entry,
            "visual_exit_type": visual_exit,
            "declared_entry_type": entry_declared,
            "declared_exit_type": exit_declared,
            "downgrade_at_entry": downgrade_entry,
            "downgrade_at_exit": downgrade_exit,
            "risk_hint": 0.8 if (downgrade_entry and downgrade_exit) else 0.65,
        }

    def _classify(self, image_url: str) -> Optional[int]:
        """通过 vehicle-ai-service 的 truck_obu 端点反推车型(declared=1 客车, 视觉为 truck 时降级)。"""
        if self._client is None or not image_url:
            return None
        try:
            result = self._client.truck_obu(image_url, declared_vehicle_type=1)
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("error"):
            return None
        is_truck = result.get("is_truck")
        if is_truck is None:
            is_truck = result.get("is_truck_vehicle")
        if is_truck is None:
            return None
        return 2 if bool(is_truck) else 1


def _is_downgrade(visual: Optional[int], declared: Optional[int]) -> bool:
    if visual is None or declared is None:
        return False
    if declared == VEHICLE_TYPE_PASSENGER and visual in TRUCK_TYPES:
        return True
    if visual > declared:
        return True
    return False


# ============================================================
# PlateObuDetector
# ============================================================


class PlateObuDetector:
    """历史聚合检测：同 plate 多 OBU / 同 OBU 多 plate

    不在单条 trip 视角上工作，由 rule_engine / task_executor 显式调用
    detect_same_plate(plate, history) 和 detect_obu_unbind(obu_id, history)。
    """

    def __init__(self, same_plate_min_obu: int = 3, obu_unbind_min_vehicles: int = 2):
        self.same_plate_min_obu = same_plate_min_obu
        self.obu_unbind_min_vehicles = obu_unbind_min_vehicles

    def detect(self, trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return None

    def detect_same_plate(
        self, plate: str, history: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        obu_ids = {t.get("entry_obu_id") for t in history if t.get("entry_obu_id")}
        obu_ids.discard(None)
        if len(obu_ids) < self.same_plate_min_obu:
            return None
        colors = {
            t.get("entry_vehicle_color")
            for t in history
            if t.get("entry_vehicle_color") is not None
        }
        types_ = {
            t.get("entry_vehicle_type")
            for t in history
            if t.get("entry_vehicle_type") is not None
        }
        return {
            "fraud_type": "SAME_PLATE_DIFF_VEHICLE",
            "plate": plate,
            "distinct_obu_count": len(obu_ids),
            "color_changes": max(0, len(colors) - 1),
            "type_changes": max(0, len(types_) - 1),
            "risk_hint": 0.75,
        }

    def detect_obu_unbind(
        self, obu_id: str, history: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        vehicles = {t.get("entry_vehicle_id") for t in history if t.get("entry_vehicle_id")}
        vehicles.discard(None)
        if len(vehicles) < self.obu_unbind_min_vehicles:
            return None
        times = sorted(
            _parse_time(t.get("entry_time")) for t in history if t.get("entry_time")
        )
        times = [t for t in times if t is not None]
        min_gap_min: Optional[float] = None
        for i in range(len(times) - 1):
            gap = (times[i + 1] - times[i]).total_seconds() / 60.0
            if min_gap_min is None or gap < min_gap_min:
                min_gap_min = gap
        return {
            "fraud_type": "OBU_UNBIND",
            "obu_id": obu_id,
            "distinct_vehicle_count": len(vehicles),
            "min_time_gap_min": min_gap_min,
            "risk_hint": 0.8 if (min_gap_min is not None and min_gap_min < 30) else 0.6,
        }


# ============================================================
# ObuShieldDetector
# ============================================================


class ObuShieldDetector:
    fraud_type = "OBU_SHIELD"

    def detect(self, trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entry_obu = trip.get("entry_obu_id")
        exit_image = trip.get("exit_image_license") or trip.get("exit_image_trans")

        has_obu = bool(entry_obu and str(entry_obu).strip())
        if has_obu or not exit_image:
            return None

        declared_type = trip.get("entry_vehicle_type")
        if declared_type not in (None, VEHICLE_TYPE_PASSENGER):
            return None

        return {
            "fraud_type": self.fraud_type,
            "no_obu": True,
            "declared_type": declared_type,
            "img_count": 1 if exit_image else 0,
            "risk_hint": 0.7 if declared_type == VEHICLE_TYPE_PASSENGER else 0.5,
        }


# ============================================================
# Registry
# ============================================================


def all_detectors() -> List[BaseDetector]:
    return [
        GatewayDetector(),
        VehicleTypeDetector(ai_client=get_client()),
        ObuShieldDetector(),
    ]
