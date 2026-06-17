"""compare_vehicles_by_passid 单元测试 — mock aggregate_trip + AuditRepository + vehicle-ai-service compare。"""
from unittest.mock import patch

from apps.api.services.vehicle_comparator import (
    _fetch_visual_features,
    compare_vehicles_by_passid,
)


def _fake_trip(passid='P1', entry_url='http://x/entry.jpg', exit_url='http://x/exit.jpg'):
    return {
        'passid': passid,
        'entry_image_license': entry_url,
        'exit_image_license': exit_url,
        'entry_vehicle_id': '京A12345',
        'exit_vehicle_id': '京A12345',
        'entry_obu_id': 'OBU-001',
        'exit_obu_id': 'OBU-001',
    }


def _fake_visual_features():
    return {
        'entry_color': 'blue',
        'exit_color': 'blue',
        'entry_visual_type': 'truck',
        'exit_visual_type': 'truck',
        'fingerprint_sim': 0.85,
    }


class TestCompareVehiclesByPassidGuards:
    def test_empty_passid_returns_image_url_missing(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip'
        ) as mock_agg:
            result = compare_vehicles_by_passid('')
        assert result['error'] == 'image_url_missing'
        assert result['field'] == 'passid'
        mock_agg.assert_not_called()

    def test_trip_not_found_returns_error_dict(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=None,
        ):
            result = compare_vehicles_by_passid('NOPE')
        assert result == {'error': 'trip_not_found'}

    def test_missing_entry_image_url(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P1',
                'entry_image_license': None,
                'exit_image_license': 'http://x/exit.jpg',
            },
        ):
            result = compare_vehicles_by_passid('P1')
        assert result['error'] == 'image_url_missing'
        assert result['field'] == 'entry_image_license'

    def test_missing_exit_image_url(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P1',
                'entry_image_license': 'http://x/entry.jpg',
                'exit_image_license': '',
            },
        ):
            result = compare_vehicles_by_passid('P1')
        assert result['error'] == 'image_url_missing'
        assert result['field'] == 'exit_image_license'


class TestCompareVehiclesByPassidHappyPath:
    def test_returns_formatted_verdict(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=_fake_trip(),
        ), patch(
            'apps.api.services.vehicle_comparator._fetch_visual_features',
            return_value=_fake_visual_features(),
        ), patch(
            'apps.api.services.vehicle_comparator.get_client'
        ) as mock_get_client:
            mock_get_client.return_value.compare.return_value = {
                'is_same_vehicle': True,
                'confidence': 0.88,
                'reason': '车牌一致',
                'model': 'qwen2.5-vl-72b',
                'elapsed_ms': 432,
            }
            result = compare_vehicles_by_passid('P1')

        assert 'error' not in result
        assert result['is_same_vehicle'] is True
        assert result['confidence'] == 0.88
        assert result['reason'] == '车牌一致'
        assert result['passid'] == 'P1'
        assert result['entry_image_url'] == 'http://x/entry.jpg'
        assert result['exit_image_url'] == 'http://x/exit.jpg'
        assert result['model'] == 'qwen2.5-vl-72b'
        assert isinstance(result['elapsed_ms'], int)

        # 校验透传给 compare 的 9 项元数据
        kwargs = mock_get_client.return_value.compare.call_args.kwargs
        assert kwargs['entry_vehicle_id'] == '京A12345'
        assert kwargs['entry_obu_id'] == 'OBU-001'
        assert kwargs['entry_color'] == 'blue'
        assert kwargs['entry_visual_type'] == 'truck'
        assert kwargs['fingerprint_sim'] == 0.85

    def test_service_error_translates_to_unavailable(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=_fake_trip(),
        ), patch(
            'apps.api.services.vehicle_comparator._fetch_visual_features',
            return_value={},
        ), patch(
            'apps.api.services.vehicle_comparator.get_client'
        ) as mock_get_client:
            mock_get_client.return_value.compare.return_value = {
                'error': 'service_unavailable',
                'detail': 'connection timeout',
            }
            result = compare_vehicles_by_passid('P1')

        assert result['error'] == 'service_unavailable'
        assert 'connection timeout' in result['detail']

    def test_service_raises_translates_to_unavailable(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=_fake_trip(),
        ), patch(
            'apps.api.services.vehicle_comparator._fetch_visual_features',
            return_value={},
        ), patch(
            'apps.api.services.vehicle_comparator.get_client'
        ) as mock_get_client:
            mock_get_client.return_value.compare.side_effect = RuntimeError('timeout')
            result = compare_vehicles_by_passid('P1')

        assert result['error'] == 'service_unavailable'
        assert 'timeout' in result['detail']

    def test_missing_fields_in_response_returns_parse_error(self):
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=_fake_trip(),
        ), patch(
            'apps.api.services.vehicle_comparator._fetch_visual_features',
            return_value={},
        ), patch(
            'apps.api.services.vehicle_comparator.get_client'
        ) as mock_get_client:
            mock_get_client.return_value.compare.return_value = {'is_same_vehicle': True}
            result = compare_vehicles_by_passid('P1')

        assert result['error'] == 'parse_error'
        assert 'confidence' in result['detail']
        assert 'reason' in result['detail']

    def test_visual_features_optional_omits_none_values(self):
        """视觉信号缺失时,只透传有值的字段给公共服务。"""
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value=_fake_trip(),
        ), patch(
            'apps.api.services.vehicle_comparator._fetch_visual_features',
            return_value={},
        ), patch(
            'apps.api.services.vehicle_comparator.get_client'
        ) as mock_get_client:
            mock_get_client.return_value.compare.return_value = {
                'is_same_vehicle': True,
                'confidence': 0.9,
                'reason': 'ok',
                'model': 'm',
            }
            compare_vehicles_by_passid('P1')

        kwargs = mock_get_client.return_value.compare.call_args.kwargs
        # 缺 visual 时只透传车牌/OBU
        assert kwargs['entry_vehicle_id'] == '京A12345'
        assert kwargs['entry_obu_id'] == 'OBU-001'
        assert kwargs.get('entry_color') is None
        assert kwargs.get('entry_visual_type') is None
        assert kwargs.get('fingerprint_sim') is None


class TestFetchVisualFeatures:
    def test_returns_empty_dict_when_audit_repo_returns_none(self):
        """audit_results 无记录时,返回空 dict(走 LLM 回退)。"""
        with patch('apps.api.services.vehicle_comparator.AuditRepository') as mock_repo:
            mock_repo.return_value.get_visual_features_by_passid.return_value = None
            assert _fetch_visual_features('NOPE') == {}

    def test_returns_extracted_fields_when_row_present(self):
        """有记录时,挑出 5 个视觉信号字段。"""
        row = {
            'entry_color': 'blue', 'exit_color': 'red',
            'entry_visual_type': 'truck', 'exit_visual_type': 'passenger',
            'fingerprint_sim': 0.77,
            'other_field': 'ignored',
        }
        with patch('apps.api.services.vehicle_comparator.AuditRepository') as mock_repo:
            mock_repo.return_value.get_visual_features_by_passid.return_value = row
            result = _fetch_visual_features('P_OK')
        assert result == {
            'entry_color': 'blue', 'exit_color': 'red',
            'entry_visual_type': 'truck', 'exit_visual_type': 'passenger',
            'fingerprint_sim': 0.77,
        }
        assert 'other_field' not in result

    def test_returns_empty_dict_when_audit_repo_raises(self):
        """AuditRepository 抛异常时,降级为空 dict(不阻断主流程)。"""
        with patch('apps.api.services.vehicle_comparator.AuditRepository') as mock_repo:
            mock_repo.return_value.get_visual_features_by_passid.side_effect = RuntimeError('db down')
            assert _fetch_visual_features('P_ERR') == {}
