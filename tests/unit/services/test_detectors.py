"""多维度检测器单元测试 — 阶段 1 MVP"""

import json
from datetime import datetime
from unittest.mock import MagicMock

from apps.api.services.detectors import (
    VEHICLE_TYPE_PASSENGER,
    VEHICLE_TYPE_TRUCK_HEAVY,
    VEHICLE_TYPE_TRUCK_LIGHT,
    GatewayDetector,
    ObuShieldDetector,
    PlateObuDetector,
    VehicleTypeDetector,
    all_detectors,
    parse_gantry_records,
)


def _gantry(records):
    return {"gantry_count": len(records), "gantry_records": records}


# ============================================================
# parse_gantry_records
# ============================================================


class TestParseGantryRecords:
    def test_handles_list_input(self):
        assert parse_gantry_records([{"a": 1}]) == [{"a": 1}]

    def test_handles_json_string(self):
        assert parse_gantry_records('[{"a": 1}]') == [{"a": 1}]

    def test_returns_empty_for_invalid_json(self):
        assert parse_gantry_records("not json") == []

    def test_returns_empty_for_none(self):
        assert parse_gantry_records(None) == []

    def test_returns_empty_for_empty_list(self):
        assert parse_gantry_records([]) == []


# ============================================================
# GatewayDetector
# ============================================================


class TestGatewayDetector:
    def test_returns_none_when_no_records(self):
        det = GatewayDetector()
        assert det.detect({"gantry_records": []}) is None
        assert det.detect({"gantry_records": None}) is None

    def test_returns_none_when_single_record(self):
        det = GatewayDetector()
        assert det.detect(_gantry([{"station_id": "A", "occur_time": "2026-01-01T00:00:00"}])) is None

    def test_detects_topology_skip(self):
        topo = [{"from_station": "A", "to_station": "B", "is_connected": 1}]
        det = GatewayDetector(topo)
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "C", "occur_time": "2026-01-01T00:10:00"},
        ]
        result = det.detect(_gantry(records))
        assert result is not None
        assert result["fraud_type"] == "GATEWAY_ANOMALY"
        assert len(result["skip_stations"]) == 1
        assert result["skip_stations"][0]["from"] == "A"
        assert result["skip_stations"][0]["to"] == "C"

    def test_detects_u_j_loop(self):
        det = GatewayDetector()
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T00:10:00"},
            {"station_id": "A", "occur_time": "2026-01-01T00:20:00"},
        ]
        result = det.detect(_gantry(records))
        assert result is not None
        assert result["loop_detected"] is True

    def test_no_skip_when_topology_empty_and_no_loop(self):
        det = GatewayDetector()
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T00:10:00"},
        ]
        assert det.detect(_gantry(records)) is None

    def test_handles_json_string_records(self):
        det = GatewayDetector([{"from_station": "A", "to_station": "B", "is_connected": 1}])
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T00:10:00"},
        ]
        result = det.detect({"gantry_records": json.dumps(records), "gantry_count": 2})
        assert result is None

    def test_risk_hint_clamped_to_one(self):
        det = GatewayDetector()
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "A", "occur_time": "2026-01-01T00:01:00"},
            {"station_id": "A", "occur_time": "2026-01-01T00:02:00"},
        ]
        result = det.detect(_gantry(records))
        assert 0.0 <= result["risk_hint"] <= 1.0


# ============================================================
# VehicleTypeDetector
# ============================================================


class TestVehicleTypeDetector:
    def test_returns_none_when_no_images(self):
        det = VehicleTypeDetector()
        assert det.detect({"entry_vehicle_type": 1}) is None

    def test_returns_none_when_no_client_and_images(self):
        det = VehicleTypeDetector(ai_client=None)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://x",
        }
        assert det.detect(trip) is None

    def test_detects_downgrade_passenger_to_truck(self):
        client = MagicMock()
        client.truck_obu.return_value = {"is_truck": True}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
            "exit_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "exit_image_license": "http://b",
        }
        result = det.detect(trip)
        assert result is not None
        assert result["fraud_type"] == "VEHICLE_TYPE_DOWNGRADE"
        assert result["visual_entry_type"] == VEHICLE_TYPE_TRUCK_LIGHT
        assert result["downgrade_at_entry"] is True
        assert result["risk_hint"] == 0.8

    def test_returns_none_on_ai_error(self):
        client = MagicMock()
        client.truck_obu.return_value = {"error": "service_unavailable"}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
        }
        assert det.detect(trip) is None

    def test_returns_none_on_ai_exception(self):
        client = MagicMock()
        client.truck_obu.side_effect = RuntimeError("boom")
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
        }
        assert det.detect(trip) is None


# ============================================================
# PlateObuDetector
# ============================================================


class TestPlateObuDetector:
    def test_detect_returns_none_single_trip_view(self):
        det = PlateObuDetector()
        assert det.detect({}) is None

    def test_detect_same_plate_below_threshold(self):
        det = PlateObuDetector(same_plate_min_obu=3)
        history = [
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU1"},
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU2"},
        ]
        assert det.detect_same_plate("京A1", history) is None

    def test_detect_same_plate_above_threshold(self):
        det = PlateObuDetector(same_plate_min_obu=3)
        history = [
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU1", "entry_vehicle_color": 1, "entry_vehicle_type": 1},
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU2", "entry_vehicle_color": 2, "entry_vehicle_type": 1},
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU3", "entry_vehicle_color": 3, "entry_vehicle_type": 2},
        ]
        result = det.detect_same_plate("京A1", history)
        assert result is not None
        assert result["fraud_type"] == "SAME_PLATE_DIFF_VEHICLE"
        assert result["distinct_obu_count"] == 3
        assert result["color_changes"] == 2
        assert result["type_changes"] == 1

    def test_detect_obu_unbind_above_threshold(self):
        det = PlateObuDetector(obu_unbind_min_vehicles=2)
        history = [
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU1", "entry_time": datetime(2026, 1, 1, 8, 0)},
            {"entry_vehicle_id": "京B2", "entry_obu_id": "OBU1", "entry_time": datetime(2026, 1, 1, 8, 20)},
        ]
        result = det.detect_obu_unbind("OBU1", history)
        assert result is not None
        assert result["fraud_type"] == "OBU_UNBIND"
        assert result["distinct_vehicle_count"] == 2
        assert result["min_time_gap_min"] == 20.0
        assert result["risk_hint"] == 0.8

    def test_detect_obu_unbind_long_gap_lower_risk(self):
        det = PlateObuDetector(obu_unbind_min_vehicles=2)
        history = [
            {"entry_vehicle_id": "A", "entry_obu_id": "X", "entry_time": datetime(2026, 1, 1, 8, 0)},
            {"entry_vehicle_id": "B", "entry_obu_id": "X", "entry_time": datetime(2026, 1, 1, 12, 0)},
        ]
        result = det.detect_obu_unbind("X", history)
        assert result["risk_hint"] == 0.6

    def test_detect_obu_unbind_below_threshold(self):
        det = PlateObuDetector(obu_unbind_min_vehicles=2)
        history = [{"entry_vehicle_id": "A", "entry_obu_id": "X", "entry_time": datetime(2026, 1, 1, 8, 0)}]
        assert det.detect_obu_unbind("X", history) is None


# ============================================================
# ObuShieldDetector
# ============================================================


class TestObuShieldDetector:
    def test_returns_none_when_obu_present(self):
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": "OBU1",
            "exit_image_license": "http://x",
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
        }
        assert det.detect(trip) is None

    def test_returns_none_when_no_exit_image(self):
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": None,
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
        }
        assert det.detect(trip) is None

    def test_returns_none_for_truck_without_obu(self):
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": None,
            "exit_image_license": "http://x",
            "entry_vehicle_type": VEHICLE_TYPE_TRUCK_HEAVY,
        }
        assert det.detect(trip) is None

    def test_detects_passenger_without_obu_with_image(self):
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": None,
            "exit_image_license": "http://x",
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
        }
        result = det.detect(trip)
        assert result is not None
        assert result["fraud_type"] == "OBU_SHIELD"
        assert result["no_obu"] is True
        assert result["risk_hint"] == 0.7

    def test_handles_empty_string_obu_as_missing(self):
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": "   ",
            "exit_image_license": "http://x",
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
        }
        result = det.detect(trip)
        assert result is not None


# ============================================================
# Registry
# ============================================================


class TestAllDetectors:
    def test_returns_three_built_in(self):
        dets = all_detectors()
        assert len(dets) == 3
        fraud_types = {d.fraud_type for d in dets}
        assert "GATEWAY_ANOMALY" in fraud_types
        assert "VEHICLE_TYPE_DOWNGRADE" in fraud_types
        assert "OBU_SHIELD" in fraud_types


# ============================================================
# _parse_time
# ============================================================


class TestParseTime:
    def test_parses_iso_string(self):
        from apps.api.services.detectors import _parse_time

        result = _parse_time("2026-06-14T10:30:00")
        assert result == datetime(2026, 6, 14, 10, 30, 0)

    def test_parses_iso_with_z_suffix(self):
        from apps.api.services.detectors import _parse_time

        result = _parse_time("2026-06-14T10:30:00Z")
        assert result is not None

    def test_returns_none_for_empty(self):
        from apps.api.services.detectors import _parse_time

        assert _parse_time(None) is None
        assert _parse_time("") is None

    def test_returns_none_for_invalid(self):
        from apps.api.services.detectors import _parse_time

        assert _parse_time("not-a-time") is None

    def test_returns_datetime_as_is(self):
        from apps.api.services.detectors import _parse_time

        dt = datetime(2026, 6, 14, 10, 0, 0)
        assert _parse_time(dt) is dt


# ============================================================
# _is_downgrade
# ============================================================


class TestIsDowngrade:
    def test_passenger_to_truck_is_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(VEHICLE_TYPE_TRUCK_LIGHT, VEHICLE_TYPE_PASSENGER) is True

    def test_same_type_not_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(1, 1) is False

    def test_visual_none_not_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(None, 1) is False

    def test_declared_none_not_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(2, None) is False

    def test_visual_greater_than_declared_is_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(4, 2) is True

    def test_visual_less_than_declared_not_downgrade(self):
        from apps.api.services.detectors import _is_downgrade

        assert _is_downgrade(1, 2) is False


# ============================================================
# _compute_avg_speed_kmh
# ============================================================


class TestComputeAvgSpeedKmh:
    def test_returns_none_for_single_record(self):
        from apps.api.services.detectors import _compute_avg_speed_kmh

        assert _compute_avg_speed_kmh([{"occur_time": "2026-01-01T00:00:00"}], {}) is None

    def test_computes_speed_with_distances(self):
        from apps.api.services.detectors import _compute_avg_speed_kmh

        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T01:00:00"},
        ]
        distances = {("A", "B"): 100.0}
        speed = _compute_avg_speed_kmh(records, distances)
        assert speed == 100.0

    def test_returns_none_when_no_distances_and_no_time(self):
        from apps.api.services.detectors import _compute_avg_speed_kmh

        records = [
            {"station_id": "A", "occur_time": None},
            {"station_id": "B", "occur_time": None},
        ]
        assert _compute_avg_speed_kmh(records, {}) is None


# ============================================================
# GatewayDetector speed anomaly
# ============================================================


class TestGatewayDetectorSpeedAnomaly:
    def test_speed_anomaly_too_slow_triggers_detection(self):
        """Speed < 10 km/h should trigger anomaly even without skip/loop."""
        from apps.api.services.detectors import GatewayDetector

        # Create a topology with a known distance that results in very slow speed
        topo = [{"from_station": "A", "to_station": "B", "is_connected": 1, "distance_km": 1.0}]
        det = GatewayDetector(topo)
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T03:00:00"},  # 3 hours for 1km = ~0.33 km/h
        ]
        result = det.detect(_gantry(records))
        assert result is not None
        assert result["fraud_type"] == "GATEWAY_ANOMALY"

    def test_normal_speed_no_anomaly(self):
        """Normal speed (10-200 km/h) with connected topology → no anomaly."""
        from apps.api.services.detectors import GatewayDetector

        topo = [{"from_station": "A", "to_station": "B", "is_connected": 1, "distance_km": 100.0}]
        det = GatewayDetector(topo)
        records = [
            {"station_id": "A", "occur_time": "2026-01-01T00:00:00"},
            {"station_id": "B", "occur_time": "2026-01-01T01:00:00"},  # 100km/h
        ]
        result = det.detect(_gantry(records))
        assert result is None


# ============================================================
# VehicleTypeDetector additional
# ============================================================


class TestVehicleTypeDetectorAdditional:
    def test_single_side_downgrade(self):
        """Only entry side downgrade → risk_hint 0.65."""
        client = MagicMock()
        client.truck_obu.return_value = {"is_truck": True}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
            "exit_vehicle_type": VEHICLE_TYPE_TRUCK_HEAVY,  # exit declared as truck → no downgrade
            "exit_image_license": "http://b",
        }
        result = det.detect(trip)
        assert result is not None
        assert result["downgrade_at_entry"] is True
        assert result["downgrade_at_exit"] is False
        assert result["risk_hint"] == 0.65

    def test_classify_returns_none_for_error_response(self):
        """AI service returns error → _classify returns None → no downgrade."""
        client = MagicMock()
        client.truck_obu.return_value = {"error": "timeout"}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
        }
        assert det.detect(trip) is None

    def test_classify_returns_none_when_is_truck_none(self):
        """AI returns is_truck=None → _classify returns None."""
        client = MagicMock()
        client.truck_obu.return_value = {"is_truck": None, "is_truck_vehicle": None}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
        }
        assert det.detect(trip) is None

    def test_classify_uses_is_truck_vehicle_fallback(self):
        """AI returns is_truck_vehicle=True (fallback field) → classify returns truck type."""
        client = MagicMock()
        client.truck_obu.return_value = {"is_truck": None, "is_truck_vehicle": True}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_license": "http://a",
        }
        result = det.detect(trip)
        assert result is not None
        assert result["visual_entry_type"] == VEHICLE_TYPE_TRUCK_LIGHT

    def test_uses_image_trans_as_fallback(self):
        """When entry_image_license is missing, uses entry_image_trans."""
        client = MagicMock()
        client.truck_obu.return_value = {"is_truck": True}
        det = VehicleTypeDetector(ai_client=client)
        trip = {
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
            "entry_image_trans": "http://a/trans.jpg",
        }
        result = det.detect(trip)
        assert result is not None


# ============================================================
# PlateObuDetector additional
# ============================================================


class TestPlateObuDetectorAdditional:
    def test_detect_same_plate_with_none_obu_ids(self):
        """None obu_ids should be discarded."""
        det = PlateObuDetector(same_plate_min_obu=2)
        history = [
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU1"},
            {"entry_vehicle_id": "京A1", "entry_obu_id": None},
            {"entry_vehicle_id": "京A1", "entry_obu_id": "OBU2"},
        ]
        result = det.detect_same_plate("京A1", history)
        assert result is not None
        assert result["distinct_obu_count"] == 2

    def test_detect_obu_unbind_with_none_times(self):
        """Entries with None entry_time should be filtered out."""
        det = PlateObuDetector(obu_unbind_min_vehicles=2)
        history = [
            {"entry_vehicle_id": "A", "entry_obu_id": "X", "entry_time": datetime(2026, 1, 1, 8, 0)},
            {"entry_vehicle_id": "B", "entry_obu_id": "X", "entry_time": None},
        ]
        # Only 1 valid time → no gap computed
        result = det.detect_obu_unbind("X", history)
        assert result is not None
        assert result["min_time_gap_min"] is None


# ============================================================
# ObuShieldDetector additional
# ============================================================


class TestObuShieldDetectorAdditional:
    def test_none_vehicle_type_with_no_obu_and_image(self):
        """declared_type=None → allowed (treated as possibly passenger)."""
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": None,
            "exit_image_license": "http://x",
            "entry_vehicle_type": None,
        }
        result = det.detect(trip)
        assert result is not None
        assert result["risk_hint"] == 0.5

    def test_uses_exit_image_trans_as_fallback(self):
        """When exit_image_license is missing, uses exit_image_trans."""
        det = ObuShieldDetector()
        trip = {
            "entry_obu_id": None,
            "exit_image_trans": "http://x/trans.jpg",
            "entry_vehicle_type": VEHICLE_TYPE_PASSENGER,
        }
        result = det.detect(trip)
        assert result is not None

    def test_batch_detect_via_protocol(self):
        """BaseDetector.batch_detect protocol calls detect for each trip."""
        det = ObuShieldDetector()
        trips = [
            {"entry_obu_id": None, "exit_image_license": "http://x", "entry_vehicle_type": VEHICLE_TYPE_PASSENGER},
            {"entry_obu_id": "OBU1", "exit_image_license": "http://x", "entry_vehicle_type": VEHICLE_TYPE_PASSENGER},
        ]
        # Manually call detect for each (simulating batch_detect from Protocol)
        results = [det.detect(t) for t in trips]
        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is None
