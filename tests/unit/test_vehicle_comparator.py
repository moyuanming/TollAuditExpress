"""compare_vehicles_by_passid 单元测试 — mock trip 聚合 + 并行下载 + MaaS 调用。"""
import os
import tempfile
from io import BytesIO
from unittest.mock import patch

from apps.api.services.vehicle_comparator import compare_vehicles_by_passid


def _fake_bytesio(content=b'fake-jpeg'):
    bio = BytesIO(content)
    bio.seek(0)
    return bio


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


class TestCompareVehiclesByPassidImageDownload:
    def test_image_download_failure_reports_per_url(self):
        url_to_bytes = {
            'http://x/entry.jpg': _fake_bytesio(),
            'http://x/exit.jpg': None,
        }
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P2',
                'entry_image_license': 'http://x/entry.jpg',
                'exit_image_license': 'http://x/exit.jpg',
            },
        ), patch(
            'apps.api.services.vehicle_comparator.download_images_parallel',
            return_value=url_to_bytes,
        ):
            result = compare_vehicles_by_passid('P2')
        assert result['error'] == 'image_download_failed'
        assert result['entry_ok'] is True
        assert result['exit_ok'] is False


class TestCompareVehiclesByPassidHappyPath:
    def test_writes_temp_files_and_cleans_up(self):
        entry_url = 'http://x/entry.jpg'
        exit_url = 'http://x/exit.jpg'
        url_to_bytes = {entry_url: _fake_bytesio(b'AAA'), exit_url: _fake_bytesio(b'BBB')}

        real_ntf = tempfile.NamedTemporaryFile
        created_paths = []

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(f.name)
            return f

        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P3',
                'entry_image_license': entry_url,
                'exit_image_license': exit_url,
            },
        ), patch(
            'apps.api.services.vehicle_comparator.download_images_parallel',
            return_value=url_to_bytes,
        ), patch(
            'apps.api.services.vehicle_comparator.tempfile.NamedTemporaryFile',
            side_effect=tracking_ntf,
        ), patch(
            'apps.api.LLM.Maas.compare_vehicles',
            return_value={
                'is_same_vehicle': True,
                'confidence': 0.88,
                'reason': '车牌一致',
                'model': 'qwen2.5-vl-72b',
            },
        ) as mock_maas:
            result = compare_vehicles_by_passid('P3')

        assert 'error' not in result
        assert result['is_same_vehicle'] is True
        assert result['confidence'] == 0.88
        assert result['reason'] == '车牌一致'
        assert result['passid'] == 'P3'
        assert result['entry_image_url'] == entry_url
        assert result['exit_image_url'] == exit_url
        assert result['model'] == 'qwen2.5-vl-72b'
        assert 'elapsed_ms' in result
        assert isinstance(result['elapsed_ms'], int)

        assert mock_maas.call_count == 1
        passed_paths = mock_maas.call_args[0]
        assert passed_paths[0] in created_paths
        assert passed_paths[1] in created_paths

        for p in created_paths:
            assert not os.path.exists(p), f"temp file leaked: {p}"

    def test_maas_returns_none_translates_to_unavailable(self):
        url_to_bytes = {
            'http://x/entry.jpg': _fake_bytesio(),
            'http://x/exit.jpg': _fake_bytesio(),
        }
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P4',
                'entry_image_license': 'http://x/entry.jpg',
                'exit_image_license': 'http://x/exit.jpg',
            },
        ), patch(
            'apps.api.services.vehicle_comparator.download_images_parallel',
            return_value=url_to_bytes,
        ), patch(
            'apps.api.LLM.Maas.compare_vehicles',
            return_value=None,
        ):
            result = compare_vehicles_by_passid('P4')
        assert result['error'] == 'maas_unavailable'
        assert 'empty result' in result['detail']

    def test_maas_raises_exception_translates_to_unavailable(self):
        url_to_bytes = {
            'http://x/entry.jpg': _fake_bytesio(),
            'http://x/exit.jpg': _fake_bytesio(),
        }
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P5',
                'entry_image_license': 'http://x/entry.jpg',
                'exit_image_license': 'http://x/exit.jpg',
            },
        ), patch(
            'apps.api.services.vehicle_comparator.download_images_parallel',
            return_value=url_to_bytes,
        ), patch(
            'apps.api.LLM.Maas.compare_vehicles',
            side_effect=RuntimeError('timeout'),
        ):
            result = compare_vehicles_by_passid('P5')
        assert result['error'] == 'maas_unavailable'
        assert 'timeout' in result['detail']

    def test_missing_fields_in_maas_response_returns_parse_error(self):
        url_to_bytes = {
            'http://x/entry.jpg': _fake_bytesio(),
            'http://x/exit.jpg': _fake_bytesio(),
        }
        with patch(
            'apps.api.services.vehicle_comparator.aggregate_trip',
            return_value={
                'passid': 'P6',
                'entry_image_license': 'http://x/entry.jpg',
                'exit_image_license': 'http://x/exit.jpg',
            },
        ), patch(
            'apps.api.services.vehicle_comparator.download_images_parallel',
            return_value=url_to_bytes,
        ), patch(
            'apps.api.LLM.Maas.compare_vehicles',
            return_value={'is_same_vehicle': True},
        ):
            result = compare_vehicles_by_passid('P6')
        assert result['error'] == 'parse_error'
        assert 'confidence' in result['detail']
        assert 'reason' in result['detail']
