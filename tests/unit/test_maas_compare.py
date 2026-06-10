"""Maas.compare_vehicles 单元测试 - mock requests.post 验证 body 构造与 JSON 解析。"""
import base64
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from apps.api.LLM import Maas
from apps.api.LLM.Maas import compare_vehicles


def _write_tmp_image(suffix='.jpg', content=b'fake-jpeg-bytes'):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, 'wb') as f:
        f.write(content)
    return path


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _ok_payload(content_str):
    return {
        'choices': [
            {'message': {'role': 'assistant', 'content': content_str}}
        ]
    }


class TestCompareVehiclesBody:
    def _capture_request(self, content='{"is_same_vehicle": true, "confidence": 0.9, "reason": "ok"}'):
        captured = {}

        def fake_post(url, headers=None, data=None, timeout=None):
            captured['url'] = url
            captured['headers'] = headers
            captured['data'] = data
            captured['timeout'] = timeout
            return _FakeResponse(_ok_payload(content))

        return captured, fake_post

    def test_body_has_two_images(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            captured, fake_post = self._capture_request()
            with patch('apps.api.core.config.MAAS_API_KEY', 'test-key', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen2.5-vl-72b', create=True), \
                 patch('apps.api.LLM.Maas.requests.post', side_effect=fake_post):
                compare_vehicles(path_a, path_b)
            payload = json.loads(captured['data'])
            content = payload['messages'][0]['content']
            image_nodes = [c for c in content if c.get('type') == 'image_url']
            assert len(image_nodes) == 2
            for node in image_nodes:
                assert node['image_url']['url'].startswith('data:image/')
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_body_uses_default_prompt_and_model(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            captured, fake_post = self._capture_request()
            with patch('apps.api.core.config.MAAS_API_KEY', 'test-key', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen2.5-vl-72b', create=True), \
                 patch('apps.api.LLM.Maas.requests.post', side_effect=fake_post):
                compare_vehicles(path_a, path_b)
            payload = json.loads(captured['data'])
            assert payload['model'] == 'qwen2.5-vl-72b'
            assert payload['temperature'] == 0.1
            assert payload['max_tokens'] == 200
            assert '<image 1>' in payload['messages'][0]['content'][0]['text']
            assert captured['headers']['Authorization'] == 'Bearer test-key'
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_png_mime_detected(self, tmp_path):
        path_a = _write_tmp_image(suffix='.png')
        path_b = _write_tmp_image(suffix='.jpg')
        try:
            captured, fake_post = self._capture_request()
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'm', create=True), \
                 patch('apps.api.LLM.Maas.requests.post', side_effect=fake_post):
                compare_vehicles(path_a, path_b)
            payload = json.loads(captured['data'])
            content = payload['messages'][0]['content']
            assert content[1]['image_url']['url'].startswith('data:image/png;base64,')
            assert content[2]['image_url']['url'].startswith('data:image/jpeg;base64,')
        finally:
            os.unlink(path_a)
            os.unlink(path_b)


class TestCompareVehiclesParsing:
    def test_parses_valid_json(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            content = '{"is_same_vehicle": true, "confidence": 0.87, "reason": "车牌一致"}'
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       return_value=_FakeResponse(_ok_payload(content))):
                result = compare_vehicles(path_a, path_b)
            assert result['is_same_vehicle'] is True
            assert result['confidence'] == 0.87
            assert result['reason'] == '车牌一致'
            assert result['model'] == 'qwen'
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_strips_markdown_json_fence(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            content = '下面是分析：\n```json\n{"is_same_vehicle": false, "confidence": 0.4, "reason": "车牌不一致"}\n```'
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       return_value=_FakeResponse(_ok_payload(content))):
                result = compare_vehicles(path_a, path_b)
            assert result['is_same_vehicle'] is False
            assert result['confidence'] == 0.4
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_invalid_json_returns_none(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       return_value=_FakeResponse(_ok_payload('not json at all'))):
                result = compare_vehicles(path_a, path_b)
            assert result is None
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_coerces_string_bool(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            content = '{"is_same_vehicle": "true", "confidence": 0.7, "reason": "ok"}'
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       return_value=_FakeResponse(_ok_payload(content))):
                result = compare_vehicles(path_a, path_b)
            assert result['is_same_vehicle'] is True
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_clamps_confidence_to_0_1(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            content = '{"is_same_vehicle": true, "confidence": 5.0, "reason": "x"}'
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       return_value=_FakeResponse(_ok_payload(content))):
                result = compare_vehicles(path_a, path_b)
            assert result['confidence'] == 1.0
        finally:
            os.unlink(path_a)
            os.unlink(path_b)


class TestCompareVehiclesGuards:
    def test_returns_none_when_no_api_key(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            with patch('apps.api.core.config.MAAS_API_KEY', '', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True):
                assert compare_vehicles(path_a, path_b) is None
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_returns_none_when_path_missing(self):
        assert compare_vehicles('', 'x.jpg') is None
        assert compare_vehicles('x.jpg', None) is None

    def test_returns_none_on_http_error(self, tmp_path):
        path_a = _write_tmp_image()
        path_b = _write_tmp_image()
        try:
            with patch('apps.api.core.config.MAAS_API_KEY', 'k', create=True), \
                 patch('apps.api.core.config.MAAS_API_URL', 'https://x', create=True), \
                 patch('apps.api.core.config.LLM_TIMEOUT', 30, create=True), \
                 patch('apps.api.core.config.MAAS_MODEL', 'qwen', create=True), \
                 patch('apps.api.LLM.Maas.requests.post',
                       side_effect=Exception('boom')):
                assert compare_vehicles(path_a, path_b) is None
        finally:
            os.unlink(path_a)
            os.unlink(path_b)
