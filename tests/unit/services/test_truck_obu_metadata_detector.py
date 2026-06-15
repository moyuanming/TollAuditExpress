"""truck_obu_metadata_detector 单元测试 — 纯元数据规则检测器

行为契约:
  - 任一侧满足 (vehicle_type ∈ {14,15,16}) AND (media_type == 1) AND (vehicle_id NOT LIKE '新A%')
  - 双侧命中 → source_side = 'BOTH'
  - 仅入口 → 'ENTRY';仅出口 → 'EXIT'
  - 不命中 → 返回 None
  - 命中时 risk_score 固定为 0.85,返回 dict 含 obu_id / media_type 透传
"""

from apps.api.services.truck_obu_metadata_detector import (
    detect_trip,
    FRAUD_TYPE,
    DEFAULT_RISK_SCORE,
)


def _trip(**fields):
    base = {
        'entry_vehicle_type': None,
        'entry_media_type': None,
        'entry_vehicle_id': None,
        'entry_obu_id': None,
        'exit_vehicle_type': None,
        'exit_media_type': None,
        'exit_vehicle_id': None,
        'exit_obu_id': None,
    }
    base.update(fields)
    return base


class TestEntrySideMatch:
    def test_entry_side_hit_returns_entry(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id='甘A11111',
            entry_obu_id='OBU-E-001',
            exit_vehicle_type=1, exit_media_type=2, exit_vehicle_id='京B22222',
        )
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'ENTRY'
        assert result['fraud_type'] == FRAUD_TYPE
        assert result['risk_score'] == DEFAULT_RISK_SCORE
        assert result['entry_obu_id'] == 'OBU-E-001'


class TestExitSideMatch:
    def test_exit_side_hit_returns_exit(self):
        trip = _trip(
            entry_vehicle_type=1, entry_media_type=2, entry_vehicle_id='京A12345',
            exit_vehicle_type=15, exit_media_type=1, exit_vehicle_id='甘B22222',
            exit_obu_id='OBU-X-002',
        )
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'EXIT'
        assert result['exit_obu_id'] == 'OBU-X-002'


class TestBothSidesMatch:
    def test_both_sides_hit_returns_both(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id='甘A11111',
            entry_obu_id='OBU-E-001',
            exit_vehicle_type=16, exit_media_type=1, exit_vehicle_id='甘C33333',
            exit_obu_id='OBU-X-003',
        )
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'BOTH'


class TestNonTruckSkipped:
    def test_passenger_car_returns_none(self):
        trip = _trip(
            entry_vehicle_type=1, entry_media_type=1, entry_vehicle_id='甘A11111',
            exit_vehicle_type=1, exit_media_type=1, exit_vehicle_id='甘A11111',
        )
        assert detect_trip(trip) is None


class TestNonObuSkipped:
    def test_mtc_media_returns_none(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=2, entry_vehicle_id='甘A11111',
            exit_vehicle_type=15, exit_media_type=2, exit_vehicle_id='甘B22222',
        )
        assert detect_trip(trip) is None


class TestNewAPrefixSkipped:
    def test_new_a_plate_returns_none(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id='新A88888',
            exit_vehicle_type=14, exit_media_type=1, exit_vehicle_id='新A88888',
        )
        assert detect_trip(trip) is None


class TestTypeOutOfRange:
    def test_type_2_returns_none(self):
        trip = _trip(
            entry_vehicle_type=2, entry_media_type=1, entry_vehicle_id='甘A11111',
            exit_vehicle_type=2, exit_media_type=1, exit_vehicle_id='甘A11111',
        )
        assert detect_trip(trip) is None

    def test_type_17_returns_none(self):
        trip = _trip(
            entry_vehicle_type=17, entry_media_type=1, entry_vehicle_id='甘A11111',
        )
        assert detect_trip(trip) is None


class TestMissingVehicleId:
    def test_entry_id_none_skips_entry_but_exit_can_hit(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id=None,
            exit_vehicle_type=14, exit_media_type=1, exit_vehicle_id='甘B22222',
        )
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'EXIT'


class TestRiskScoreFixed:
    def test_risk_score_constant(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id='甘A11111',
        )
        result = detect_trip(trip)
        assert result['risk_score'] == 0.85


class TestResultStructure:
    def test_result_dict_keys(self):
        trip = _trip(
            entry_vehicle_type=14, entry_media_type=1, entry_vehicle_id='甘A11111',
            entry_obu_id='OBU-001',
            exit_vehicle_type=15, exit_media_type=1, exit_vehicle_id='甘B22222',
            exit_obu_id='OBU-002',
        )
        result = detect_trip(trip)
        for key in (
            'fraud_type', 'source_side',
            'entry_vehicle_type', 'exit_vehicle_type',
            'entry_media_type', 'exit_media_type',
            'entry_obu_id', 'exit_obu_id', 'risk_score',
        ):
            assert key in result
