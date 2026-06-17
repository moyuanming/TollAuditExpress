"""download_image / download_images_parallel 测试 — 验证 retry 与并行下载行为。"""
from io import BytesIO
from unittest.mock import MagicMock, patch

import requests

from apps.api.services.image_utils import download_image, download_images_parallel


def _fake_response(status=200, content_type='image/jpeg', body=b'jpeg-bytes'):
    r = MagicMock()
    r.status_code = status
    r.headers = {'Content-Type': content_type}
    r.content = body
    return r


class TestDownloadImageRetry:
    def test_succeeds_first_try(self):
        with patch(
            'apps.api.services.image_utils.requests.get',
            return_value=_fake_response(),
        ) as mock_get:
            result = download_image('http://x/a.jpg', timeout=5)
        assert isinstance(result, BytesIO)
        assert result.getvalue() == b'jpeg-bytes'
        assert mock_get.call_count == 1

    def test_retries_on_request_exception(self):
        responses = [
            requests.ConnectionError('boom'),
            requests.ConnectionError('boom2'),
            _fake_response(),
        ]

        def side_effect(*args, **kwargs):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch(
            'apps.api.services.image_utils.requests.get',
            side_effect=side_effect,
        ), patch('apps.api.services.image_utils.time.sleep'):
            result = download_image('http://x/a.jpg', timeout=5)
        assert isinstance(result, BytesIO)
        assert result.getvalue() == b'jpeg-bytes'

    def test_retries_on_non_image_response(self):
        bad = _fake_response(status=200, content_type='text/html', body=b'not an image')
        good = _fake_response()
        with patch(
            'apps.api.services.image_utils.requests.get',
            side_effect=[bad, bad, good],
        ), patch('apps.api.services.image_utils.time.sleep'):
            result = download_image('http://x/a.jpg', timeout=5)
        assert isinstance(result, BytesIO)

    def test_returns_none_after_all_retries_exhausted(self):
        with patch(
            'apps.api.services.image_utils.requests.get',
            side_effect=requests.ConnectionError('always-fail'),
        ), patch('apps.api.services.image_utils.time.sleep'):
            result = download_image('http://x/a.jpg', timeout=5)
        assert result is None

    def test_returns_none_for_empty_url(self):
        assert download_image('', timeout=5) is None
        assert download_image(None, timeout=5) is None

    def test_respects_retries_config(self):
        with patch(
            'apps.api.services.image_utils.IMAGE_DOWNLOAD_RETRIES',
            1,
        ), patch(
            'apps.api.services.image_utils.requests.get',
            side_effect=requests.ConnectionError('fail'),
        ), patch('apps.api.services.image_utils.time.sleep'):
            result = download_image('http://x/a.jpg', timeout=5)
        assert result is None


class TestDownloadImagesParallel:
    def test_returns_dict_keyed_by_url(self):
        urls = ['http://x/a.jpg', 'http://x/b.jpg']
        with patch(
            'apps.api.services.image_utils.download_image',
            side_effect=[BytesIO(b'A'), BytesIO(b'B')],
        ):
            results = download_images_parallel(urls, max_workers=2)
        assert set(results.keys()) == set(urls)
        assert results['http://x/a.jpg'].getvalue() == b'A'
        assert results['http://x/b.jpg'].getvalue() == b'B'

    def test_partial_failure_returns_none_for_failed(self):
        urls = ['http://x/a.jpg', 'http://x/b.jpg']
        with patch(
            'apps.api.services.image_utils.download_image',
            side_effect=[BytesIO(b'A'), None],
        ):
            results = download_images_parallel(urls, max_workers=2)
        assert results['http://x/a.jpg'].getvalue() == b'A'
        assert results['http://x/b.jpg'] is None

    def test_empty_input_returns_empty_dict(self):
        assert download_images_parallel([]) == {}
        assert download_images_parallel(['', None]) == {}

    def test_exception_in_one_url_does_not_block_others(self):
        urls = ['http://x/a.jpg', 'http://x/b.jpg']
        with patch(
            'apps.api.services.image_utils.download_image',
            side_effect=[BytesIO(b'A'), RuntimeError('boom')],
        ):
            results = download_images_parallel(urls, max_workers=2)
        assert results['http://x/a.jpg'].getvalue() == b'A'
        assert results['http://x/b.jpg'] is None
