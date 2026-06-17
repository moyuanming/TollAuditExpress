"""vehicle-ai-service HTTP 客户端。

提供：
- get_client() 单例
- VehicleAIClient.compare(image_url_a, image_url_b, **metadata)
    把廉价信号（车牌/OBU/颜色/车型/fingerprint_sim/车牌OCR）随请求体透传，
    让侧车在分档裁决器中尽量绕开 LLM 调用。
- VehicleAIClient.entry_exit(entry_url, exit_url)
    出入口车辆比对
- VehicleAIClient.classify_truck(image_url)
    纯 ML 视觉车型分类(无 LLM),客车 OBU 监测的第一步
- VehicleAIClient.llm_verify_truck(image_url, ml_is_truck, ml_confidence)
    LLM 二次复核,客车 OBU 监测的第二步(只在 ML 判是货车时调用)
- VehicleAIClient.truck_obu(image_url, declared_vehicle_type=1)
    货车套用客车OBU检测(复合端点,旧路径兼容)
- VehicleAIClient.recognize_plate(image_url)
    车牌 OCR 识别
"""

from typing import Any

import httpx

from apps.api.core.config import VEHICLE_AI_SERVICE_TIMEOUT, VEHICLE_AI_SERVICE_URL
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


class VehicleAIClient:
    def __init__(
        self,
        base_url: str = VEHICLE_AI_SERVICE_URL,
        timeout_s: float = VEHICLE_AI_SERVICE_TIMEOUT,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout_s = timeout_s

    def compare(
        self,
        image_url_a: str,
        image_url_b: str,
        *,
        entry_vehicle_id: str | None = None,
        exit_vehicle_id: str | None = None,
        entry_obu_id: str | None = None,
        exit_obu_id: str | None = None,
        entry_color: str | None = None,
        exit_color: str | None = None,
        entry_visual_type: str | None = None,
        exit_visual_type: str | None = None,
        fingerprint_sim: float | None = None,
        entry_plate_ocr: str | None = None,
        exit_plate_ocr: str | None = None,
        plate_match: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'image_url_a': image_url_a,
            'image_url_b': image_url_b,
        }
        for key, value in (
            ('entry_vehicle_id', entry_vehicle_id),
            ('exit_vehicle_id', exit_vehicle_id),
            ('entry_obu_id', entry_obu_id),
            ('exit_obu_id', exit_obu_id),
            ('entry_color', entry_color),
            ('exit_color', exit_color),
            ('entry_visual_type', entry_visual_type),
            ('exit_visual_type', exit_visual_type),
            ('fingerprint_sim', fingerprint_sim),
            ('entry_plate_ocr', entry_plate_ocr),
            ('exit_plate_ocr', exit_plate_ocr),
            ('plate_match', plate_match),
        ):
            if value is not None:
                payload[key] = value

        return self._post('/api/v1/vehicle/compare', payload)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, json=payload)
        except httpx.HTTPError as e:
            logger.error(
                'vehicle_ai_client: HTTP error url=%s timeout=%ss err=%s',
                url, self.timeout_s, e,
            )
            return {'error': 'service_unavailable', 'detail': str(e), 'url': url}

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                'vehicle_ai_client: non-JSON response url=%s status=%d body=%s',
                url, resp.status_code, resp.text[:200],
            )
            return {
                'error': 'parse_error',
                'detail': f'status={resp.status_code} non-JSON',
                'url': url,
            }

        if resp.status_code != 200:
            detail = data.get('detail') if isinstance(data, dict) else None
            if detail is None:
                detail = data
            logger.error(
                'vehicle_ai_client: non-200 response url=%s status=%d body=%s',
                url, resp.status_code, str(detail)[:200],
            )
            return {'error': 'service_unavailable', 'detail': detail, 'url': url}

        return data

    def _post_multipart(self, path: str, fields: dict[str, Any]) -> dict[str, Any]:
        """multipart/form-data POST — 用于 recognize-plate / plate 等仅接受表单的端点。"""
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, data=fields)
        except httpx.HTTPError as e:
            logger.error(
                'vehicle_ai_client: HTTP error url=%s timeout=%ss err=%s',
                url, self.timeout_s, e,
            )
            return {'error': 'service_unavailable', 'detail': str(e), 'url': url}

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                'vehicle_ai_client: non-JSON response url=%s status=%d body=%s',
                url, resp.status_code, resp.text[:200],
            )
            return {
                'error': 'parse_error',
                'detail': f'status={resp.status_code} non-JSON',
                'url': url,
            }

        if resp.status_code != 200:
            detail = data.get('detail') if isinstance(data, dict) else None
            if detail is None:
                detail = data
            logger.error(
                'vehicle_ai_client: non-200 response url=%s status=%d body=%s',
                url, resp.status_code, str(detail)[:200],
            )
            return {'error': 'service_unavailable', 'detail': detail, 'url': url}

        return data

    def recognize_plate(self, image_url: str) -> dict[str, Any]:
        """车牌 OCR 识别 — 从图片中识别车牌号。

        端点仅接受 multipart/form-data(application/json 会被拒,返回
        422 missing_input),因此走 _post_multipart 通道。
        """
        return self._post_multipart('/api/v1/vehicle/recognize-plate', {
            'image_url': image_url,
        })

    def entry_exit(self, entry_url: str, exit_url: str) -> dict[str, Any]:
        """出入口车辆比对 — 判断入出口是否为同一辆车。"""
        return self._post('/api/v1/vehicle/entry-exit', {
            'entry_image_url': entry_url,
            'exit_image_url': exit_url,
        })

    def truck_obu(
        self,
        image_url: str,
        *,
        declared_vehicle_type: int = 1,
    ) -> dict[str, Any]:
        """货车套用客车OBU检测 — 判断客车记录的图片是否实为货车。

        复合端点(ML+LLM),旧路径兼容。新代码请优先用 ``classify_truck`` +
        ``llm_verify_truck`` 两步调用,避免 ML 高自信时漏调 LLM 的旧 BUG。
        """
        return self._post('/api/v1/vehicle/truck-obu', {
            'image_url': image_url,
            'declared_vehicle_type': declared_vehicle_type,
        })

    def classify_truck(self, image_url: str) -> dict[str, Any]:
        """纯 ML 视觉车型分类 — 第一步,失败/拒收一律返回 ``is_truck=False``。

        端点契约:不抛 5xx。返回字段 ``is_truck`` / ``confidence`` /
        ``visual_vehicle_type``。``is_truck=False`` 时调用方无需再调 LLM。
        """
        return self._post('/api/v1/vehicle/classify-truck', {
            'image_url': image_url,
        })

    def llm_verify_truck(
        self,
        image_url: str,
        *,
        ml_is_truck: bool,
        ml_confidence: float,
    ) -> dict[str, Any]:
        """LLM 二次复核 — 第二步,仅在 classify_truck 返回 is_truck=True 时调用。

        返回字段 ``is_truck`` (Optional[bool]) / ``confidence`` / ``llm_verified``
        / ``llm_reason`` / ``llm_error``。``llm_verified=False`` 时一律 drop,
        无论 ``llm_error='maas_unavailable'``(MaaS 抖动)还是其他原因。
        """
        return self._post('/api/v1/vehicle/llm-verify-truck', {
            'image_url': image_url,
            'ml_is_truck': ml_is_truck,
            'ml_confidence': ml_confidence,
        })


_client: VehicleAIClient | None = None


def get_client() -> VehicleAIClient:
    global _client
    if _client is None:
        _client = VehicleAIClient()
    return _client
