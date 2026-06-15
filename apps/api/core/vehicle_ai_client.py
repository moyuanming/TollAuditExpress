"""vehicle-ai-service HTTP 客户端。

提供：
- get_client() 单例
- VehicleAIClient.compare(image_url_a, image_url_b, **metadata)
    把廉价信号（车牌/OBU/颜色/车型/fingerprint_sim/车牌OCR）随请求体透传，
    让侧车在分档裁决器中尽量绕开 LLM 调用。
- VehicleAIClient.entry_exit(entry_url, exit_url)
    出入口车辆比对
- VehicleAIClient.truck_obu(image_url, declared_vehicle_type=1)
    货车套用客车OBU检测
- VehicleAIClient.recognize_plate(image_url)
    车牌 OCR 识别
"""

from typing import Any, Dict, Optional

import httpx

from apps.api.core.config import VEHICLE_AI_SERVICE_URL, VEHICLE_AI_SERVICE_TIMEOUT
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
        entry_vehicle_id: Optional[str] = None,
        exit_vehicle_id: Optional[str] = None,
        entry_obu_id: Optional[str] = None,
        exit_obu_id: Optional[str] = None,
        entry_color: Optional[str] = None,
        exit_color: Optional[str] = None,
        entry_visual_type: Optional[str] = None,
        exit_visual_type: Optional[str] = None,
        fingerprint_sim: Optional[float] = None,
        entry_plate_ocr: Optional[str] = None,
        exit_plate_ocr: Optional[str] = None,
        plate_match: Optional[bool] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
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

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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

    def recognize_plate(self, image_url: str) -> Dict[str, Any]:
        """车牌 OCR 识别 — 从图片中识别车牌号。"""
        return self._post('/api/v1/vehicle/recognize-plate', {
            'image_url': image_url,
        })

    def entry_exit(self, entry_url: str, exit_url: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """货车套用客车OBU检测 — 判断客车记录的图片是否实为货车。"""
        return self._post('/api/v1/vehicle/truck-obu', {
            'image_url': image_url,
            'declared_vehicle_type': declared_vehicle_type,
        })


_client: Optional[VehicleAIClient] = None


def get_client() -> VehicleAIClient:
    global _client
    if _client is None:
        _client = VehicleAIClient()
    return _client
