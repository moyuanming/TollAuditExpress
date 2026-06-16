"""image_utils 单元测试 — 图片下载公共工具

行为契约:
  - download_image: 空 URL → None; requests 不可用 → None
  - download_image: 正常 200 image/* → BytesIO
  - download_image: 非 image 响应 → 重试后 None
  - download_image: RequestException → 重试后 None
  - download_images_parallel: 空 URL 列表 → {}
  - download_images_parallel: 并行下载,失败 URL 值为 None
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

from apps.api.services.image_utils import (
    _is_image_response,
    _proxies_for,
    download_image,
    download_images_parallel,
)

# ============================================================
# _is_image_response
# ============================================================


class TestIsImageResponse:
    def test_200_with_image_content_type_returns_true(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        assert _is_image_response(resp) is True

    def test_200_with_non_image_content_type_returns_false(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "text/html"}
        assert _is_image_response(resp) is False

    def test_404_with_image_content_type_returns_false(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.headers = {"Content-Type": "image/jpeg"}
        assert _is_image_response(resp) is False

    def test_missing_content_type_header_returns_false(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        assert _is_image_response(resp) is False


# ============================================================
# _proxies_for
# ============================================================


class TestProxiesFor:
    def test_internal_ip_returns_no_proxy(self):
        result = _proxies_for("http://10.165.83.43/image.jpg")
        assert result == {"http": None, "https": None}

    def test_internal_ip_https_returns_no_proxy(self):
        result = _proxies_for("https://10.1.2.3/image.jpg")
        assert result == {"http": None, "https": None}

    def test_external_ip_returns_none(self):
        assert _proxies_for("http://example.com/image.jpg") is None

    def test_localhost_returns_none(self):
        assert _proxies_for("http://localhost/image.jpg") is None


# ============================================================
# download_image
# ============================================================


class TestDownloadImage:
    def test_empty_url_returns_none(self):
        assert download_image("") is None

    def test_none_url_returns_none(self):
        assert download_image(None) is None

    @patch("apps.api.services.image_utils.HAS_REQUESTS", False)
    def test_no_requests_library_returns_none(self):
        assert download_image("http://example.com/img.jpg") is None

    @patch("apps.api.services.image_utils._attempt_once")
    @patch("apps.api.services.image_utils.HAS_REQUESTS", True)
    def test_successful_download_returns_bytesio(self, mock_attempt):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.content = b"\xff\xd8\xff\xe0fake_jpeg"
        mock_attempt.return_value = resp

        result = download_image("http://example.com/img.jpg")
        assert result is not None
        assert isinstance(result, BytesIO)
        assert result.read() == b"\xff\xd8\xff\xe0fake_jpeg"

    @patch("apps.api.services.image_utils.time.sleep")
    @patch("apps.api.services.image_utils._attempt_once")
    @patch("apps.api.services.image_utils.HAS_REQUESTS", True)
    def test_non_image_response_retries_and_returns_none(self, mock_attempt, mock_sleep):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "text/html"}
        mock_attempt.return_value = resp

        result = download_image("http://example.com/not_image")
        assert result is None
        # Should have retried (default retries=3)
        assert mock_attempt.call_count == 3

    @patch("apps.api.services.image_utils.time.sleep")
    @patch("apps.api.services.image_utils._attempt_once")
    @patch("apps.api.services.image_utils.HAS_REQUESTS", True)
    def test_request_exception_retries_and_returns_none(self, mock_attempt, mock_sleep):
        import requests as req

        mock_attempt.side_effect = req.RequestException("timeout")

        result = download_image("http://example.com/img.jpg")
        assert result is None
        assert mock_attempt.call_count == 3

    @patch("apps.api.services.image_utils._attempt_once")
    @patch("apps.api.services.image_utils.HAS_REQUESTS", True)
    def test_succeeds_on_second_attempt(self, mock_attempt):
        import requests as req

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.headers = {"Content-Type": "image/png"}
        resp_ok.content = b"png_data"

        mock_attempt.side_effect = [
            req.RequestException("first fail"),
            resp_ok,
        ]

        with patch("apps.api.services.image_utils.time.sleep"):
            result = download_image("http://example.com/img.jpg")

        assert result is not None
        assert result.read() == b"png_data"

    @patch("apps.api.services.image_utils._attempt_once")
    @patch("apps.api.services.image_utils.HAS_REQUESTS", True)
    def test_custom_timeout_passed_to_attempt(self, mock_attempt):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.content = b"data"
        mock_attempt.return_value = resp

        download_image("http://example.com/img.jpg", timeout=30)
        mock_attempt.assert_called_once_with("http://example.com/img.jpg", 30)


# ============================================================
# download_images_parallel
# ============================================================


class TestDownloadImagesParallel:
    def test_empty_url_list_returns_empty_dict(self):
        assert download_images_parallel([]) == {}

    def test_none_urls_filtered_out(self):
        result = download_images_parallel([None, "", "http://example.com/img.jpg"])
        assert len(result) == 1
        assert "http://example.com/img.jpg" in result

    @patch("apps.api.services.image_utils.HAS_REQUESTS", False)
    def test_no_requests_returns_none_for_each_url(self):
        result = download_images_parallel(["http://a.com/1.jpg", "http://b.com/2.jpg"])
        assert result == {"http://a.com/1.jpg": None, "http://b.com/2.jpg": None}

    @patch("apps.api.services.image_utils.download_image")
    def test_parallel_download_success(self, mock_download):
        fake_bytes = BytesIO(b"img_data")
        mock_download.return_value = fake_bytes

        result = download_images_parallel(["http://a.com/1.jpg", "http://b.com/2.jpg"])
        assert result["http://a.com/1.jpg"] is fake_bytes
        assert result["http://b.com/2.jpg"] is fake_bytes

    @patch("apps.api.services.image_utils.download_image")
    def test_parallel_download_partial_failure(self, mock_download):
        fake_bytes = BytesIO(b"img_data")
        mock_download.side_effect = [fake_bytes, None]

        result = download_images_parallel(["http://a.com/1.jpg", "http://b.com/2.jpg"])
        assert result["http://a.com/1.jpg"] is fake_bytes
        assert result["http://b.com/2.jpg"] is None

    @patch("apps.api.services.image_utils.download_image")
    def test_parallel_download_exception_in_future(self, mock_download):
        mock_download.side_effect = RuntimeError("unexpected")

        result = download_images_parallel(["http://a.com/1.jpg"])
        assert result["http://a.com/1.jpg"] is None
