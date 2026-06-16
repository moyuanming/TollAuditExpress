"""PassengerObuDetector 单元测试 — 元数据预筛 + 图片识别 + LLM 复核 三段式

行为契约:
  - 元数据预筛失败(vt≠1 / 车牌新A / image 为空) → 不命中
  - visual_type 已有且不是货车 → 跳过(免一次模型调用)
  - 公共服务返回 error / 异常 / is_suspicious=False / llm_verified=False → 不命中
  - 单侧命中 → source_side = ENTRY/EXIT
  - 双侧命中 → source_side = BOTH, llm_verified AND, llm_confidence 平均
"""

import pytest
from unittest.mock import MagicMock

from apps.api.services.passenger_obu_detector import (
    detect_trip,
    FRAUD_TYPE,
    DECLARED_VEHICLE_TYPE,
    TRUCK_VISUAL_TYPES,
    NON_NEW_A_PREFIX,
)


# ============================================================
# Helpers
# ============================================================


def _base_trip(**overrides):
    """构建一个默认会命中单侧(入口)的 trip 字典。"""
    trip = {
        'entry_vehicle_type': DECLARED_VEHICLE_TYPE,
        'entry_vehicle_id': '川A12345',
        'entry_visual_type': None,
        'entry_image_trans': 'http://example.com/entry_trans.jpg',
        'entry_obu_id': 'OBU001',
        'entry_media_type': 1,
        'exit_vehicle_type': 2,
        'exit_vehicle_id': '川A12345',
        'exit_visual_type': None,
        'exit_image_trans': None,
        'exit_obu_id': None,
        'exit_media_type': None,
    }
    trip.update(overrides)
    return trip


def _hit_response(**overrides):
    resp = {
        'is_suspicious': True,
        'fraud_type': FRAUD_TYPE,
        'visual_vehicle_type': 'truck',
        'is_truck': True,
        'confidence': 0.95,
        'llm_verified': True,
        'llm_confidence': 0.93,
    }
    resp.update(overrides)
    return resp


# ============================================================
# metadata 预筛
# ============================================================


class TestMetadataPrefilter:
    def test_entry_vt_not_passenger(self, mock_ai_client):
        """申报 vehicle_type≠1 → 不命中,且不调公共服务"""
        trip = _base_trip(entry_vehicle_type=2)
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_exit_vt_not_passenger(self, mock_ai_client):
        """两侧 vehicle_type≠1 → 不命中,且不调公共服务"""
        trip = _base_trip(entry_vehicle_type=2, exit_vehicle_type=14)
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_entry_vehicle_id_empty(self, mock_ai_client):
        trip = _base_trip(entry_vehicle_id=None)
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_entry_vehicle_id_new_a_prefix(self, mock_ai_client):
        """车牌以'新A'开头 → 不命中"""
        trip = _base_trip(entry_vehicle_id='新A12345')
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_exit_vehicle_id_new_a_prefix(self, mock_ai_client):
        """出口车牌以新A 开头,入口不命中则整个 trip 不命中(因为单侧也走失败路径)"""
        trip = _base_trip(exit_vehicle_type=1, exit_vehicle_id='新A99999')
        # 入口元数据 OK → 入口会调公共服务
        # 出口元数据 fail(新A)→ 出口跳过
        # 所以单侧仍可能命中,但出口侧不命中
        mock_ai_client.truck_obu.return_value = _hit_response()
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'ENTRY'
        # 入口侧被调,出口侧不调(因元数据 fail)
        assert mock_ai_client.truck_obu.call_count == 1

    def test_entry_image_empty(self, mock_ai_client):
        trip = _base_trip(entry_image_trans=None)
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_existing_visual_type_is_passenger_skips_service(self, mock_ai_client):
        """已记录 visual_type=客车 → 跳过公共服务,免一次模型调用"""
        trip = _base_trip(entry_visual_type='1')
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_existing_visual_type_is_truck_proceeds(self, mock_ai_client):
        """已记录 visual_type=货车 → 仍调公共服务走 LLM 复核"""
        trip = _base_trip(entry_visual_type='truck')
        mock_ai_client.truck_obu.return_value = _hit_response()
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'ENTRY'
        mock_ai_client.truck_obu.assert_called_once()

    def test_existing_visual_type_other_string_skips(self, mock_ai_client):
        trip = _base_trip(entry_visual_type='bus')  # 不在 TRUCK_VISUAL_TYPES 中
        assert detect_trip(trip) is None
        mock_ai_client.truck_obu.assert_not_called()


# ============================================================
# 公共服务响应分支
# ============================================================


class TestPublicServiceResponse:
    def test_error_key_no_hit(self, mock_ai_client):
        trip = _base_trip()
        mock_ai_client.truck_obu.return_value = {'error': 'timeout'}
        assert detect_trip(trip) is None

    def test_is_suspicious_false_no_hit(self, mock_ai_client):
        trip = _base_trip()
        mock_ai_client.truck_obu.return_value = _hit_response(is_suspicious=False)
        assert detect_trip(trip) is None

    def test_is_suspicious_true_with_llm_unverified_hits(self, mock_ai_client):
        """is_suspicious=True 即使 llm_verified=False(ML 高自信不调 LLM)也命中。

        背景:AI service 在 ML 高度自信(>= 0.85)时不调 LLM,llm_verified 留 False。
        我方应以 is_suspicious 为准,不能把 llm_verified 当硬门坎。
        """
        trip = _base_trip()
        mock_ai_client.truck_obu.return_value = _hit_response(
            llm_verified=False, is_suspicious=True,
        )
        result = detect_trip(trip)
        assert result is not None
        assert result['source_side'] == 'ENTRY'
        # 仍把 llm_verified 透传给调用方,作为审计 metadata
        assert result['llm_verified'] is False

    def test_exception_in_service_no_hit(self, mock_ai_client):
        trip = _base_trip()
        mock_ai_client.truck_obu.side_effect = RuntimeError('network error')
        # 不应抛异常,也不命中
        assert detect_trip(trip) is None


# ============================================================
# 命中分支
# ============================================================


class TestSingleSideHit:
    def test_entry_only_hit(self, mock_ai_client):
        trip = _base_trip()
        mock_ai_client.truck_obu.return_value = _hit_response()
        result = detect_trip(trip)

        assert result is not None
        assert result['fraud_type'] == FRAUD_TYPE
        assert result['source_side'] == 'ENTRY'
        assert result['llm_verified'] is True
        # conftest mock 默认 confidence=0.95 → detector 把它求平均
        assert result['llm_confidence'] == pytest.approx(0.95)
        assert result['visual_vehicle_type'] == 'truck'
        # 单侧命中 risk_score 0.85
        assert result['risk_score'] == 0.85
        # 入口被调,出口无 image 不调
        assert mock_ai_client.truck_obu.call_count == 1
        called_url = mock_ai_client.truck_obu.call_args[0][0]
        assert called_url == trip['entry_image_trans']

    def test_exit_only_hit(self, mock_ai_client):
        """入口无 image(元数据预筛失败),出口命中 → source_side=EXIT"""
        trip = _base_trip(
            entry_vehicle_type=2,  # 入口不满足 vt=1
            exit_vehicle_type=1,
            exit_vehicle_id='川A99999',
            exit_visual_type=None,
            exit_image_trans='http://example.com/exit_trans.jpg',
            exit_obu_id='OBU002',
            exit_media_type=1,
        )
        mock_ai_client.truck_obu.return_value = _hit_response()
        result = detect_trip(trip)

        assert result is not None
        assert result['source_side'] == 'EXIT'
        assert result['risk_score'] == 0.85
        # 入口被 skip(因 vt≠1),只出口被调
        assert mock_ai_client.truck_obu.call_count == 1
        called_url = mock_ai_client.truck_obu.call_args[0][0]
        assert called_url == trip['exit_image_trans']

    def test_declared_vehicle_type_passed_to_service(self, mock_ai_client):
        trip = _base_trip()
        mock_ai_client.truck_obu.return_value = _hit_response()
        detect_trip(trip)
        # 必须以 declared_vehicle_type=1 调用
        kwargs = mock_ai_client.truck_obu.call_args.kwargs
        assert kwargs.get('declared_vehicle_type') == DECLARED_VEHICLE_TYPE


class TestDualSideHit:
    def test_both_sides_hit(self, mock_ai_client):
        trip = _base_trip(
            exit_vehicle_type=1,
            exit_vehicle_id='川A12345',
            exit_visual_type=None,
            exit_image_trans='http://example.com/exit_trans.jpg',
            exit_obu_id='OBU002',
            exit_media_type=1,
        )
        # 两次调用都返回命中(但 confidence 不同,以验证求平均)
        mock_ai_client.truck_obu.side_effect = [
            _hit_response(confidence=0.95),
            _hit_response(confidence=0.90, llm_confidence=0.88),
        ]
        result = detect_trip(trip)

        assert result is not None
        assert result['source_side'] == 'BOTH'
        assert result['llm_verified'] is True
        # detector 用 resp['confidence'] 求平均;(0.95 + 0.90) / 2 = 0.925
        assert result['llm_confidence'] == pytest.approx(0.925)
        # 双侧 risk_score 0.95
        assert result['risk_score'] == 0.95
        # 入口和出口都调了一次
        assert mock_ai_client.truck_obu.call_count == 2

    def test_both_hit_with_one_llm_unverified(self, mock_ai_client):
        """双侧 is_suspicious=True(其中一侧 llm_verified=False)→ 双侧命中,
        detector 层的 llm_verified 取 AND → 整体 llm_verified=False。
        """
        trip = _base_trip(
            exit_vehicle_type=1,
            exit_vehicle_id='川A12345',
            exit_image_trans='http://example.com/exit_trans.jpg',
            exit_obu_id='OBU002',
            exit_media_type=1,
        )
        mock_ai_client.truck_obu.side_effect = [
            _hit_response(llm_verified=True, llm_confidence=0.95),
            _hit_response(llm_verified=False, llm_confidence=0.80, is_suspicious=True),
        ]
        result = detect_trip(trip)

        # 双侧都命中(都不再被 llm_verified 过滤)
        assert result is not None
        assert result['source_side'] == 'BOTH'
        # 整体 llm_verified = True AND False = False
        assert result['llm_verified'] is False
        assert mock_ai_client.truck_obu.call_count == 2


# ============================================================
# 字段透传
# ============================================================


class TestFieldPassthrough:
    def test_result_contains_all_required_fields(self, mock_ai_client):
        trip = _base_trip(
            entry_obu_id='OBU-X',
            exit_obu_id='OBU-Y',
        )
        mock_ai_client.truck_obu.return_value = _hit_response()
        result = detect_trip(trip)

        assert result['entry_vehicle_type'] == DECLARED_VEHICLE_TYPE
        assert result['exit_vehicle_type'] == 2
        assert result['entry_obu_id'] == 'OBU-X'
        assert result['exit_obu_id'] == 'OBU-Y'
        assert result['entry_image_trans'] == trip['entry_image_trans']
        assert result['entry_visual_type'] is None
        assert result['exit_visual_type'] is None

    def test_constants_exposed(self):
        """对外常量应保持稳定(下游 task_executor / 路由都引用)"""
        assert FRAUD_TYPE == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A'
        assert DECLARED_VEHICLE_TYPE == 1
        assert NON_NEW_A_PREFIX == '新A'
        assert 'truck' in TRUCK_VISUAL_TYPES
        assert '14' in TRUCK_VISUAL_TYPES
