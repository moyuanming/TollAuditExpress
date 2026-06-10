import base64
import json
import re
from typing import Optional

import requests
from apps.api.LLM.Prompt import prompt, compare_vehicles_prompt
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


def detect_truck(image_path):
    """
    检测单张图片是否为货车（使用 ModelArts MaaS API）

    Args:
        image_path (str): 图片文件的完整路径

    Returns:
        int or None:
            1: 是货车
            0: 不是货车
            None: 检测失败
    """
    try:
        with open(image_path, "rb") as image_file:
            base64_data = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error("图片读取失败: %s", e)
        return None

    # 获取 API 配置
    from apps.api.core.config import MAAS_API_KEY, MAAS_MODEL, MAAS_API_URL, LLM_TIMEOUT
    api_key = MAAS_API_KEY
    model_name = MAAS_MODEL
    api_url = MAAS_API_URL

    if not api_key:
        logger.warning("未配置 maas_api_key")
        return None

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }

        # 自动检测图片格式
        ext = image_path.lower().split('.')[-1]
        if ext == 'jpg' or ext == 'jpeg':
            mime_type = "image/jpeg"
        elif ext == 'png':
            mime_type = "image/png"
        elif ext == 'webp':
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

        data = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }

        timeout = LLM_TIMEOUT
        response = requests.post(
            api_url,
            headers=headers,
            data=json.dumps(data),
            timeout=timeout
        )

        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"].strip()
            if '1' in content:
                return 1
            elif '0' in content:
                return 0
            else:
                logger.warning("无法解析响应 %s: %s", image_path, content)
                return None
        else:
            logger.warning("API响应异常 %s: %s", image_path, result)
            return None

    except Exception as e:
        logger.error("API请求失败 %s: %s", image_path, e)
        return None


def _mime_for_path(path: str) -> str:
    ext = (path or '').lower().rsplit('.', 1)[-1]
    if ext in ('jpg', 'jpeg'):
        return 'image/jpeg'
    if ext == 'png':
        return 'image/png'
    if ext == 'webp':
        return 'image/webp'
    return 'image/jpeg'


def _encode_image(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def _parse_compare_payload(content: str) -> dict:
    """从 MaaS 响应文本中抽取 JSON 对象。容忍 ```json``` 包裹或多余前导文字。"""
    if not content:
        return {}
    text = content.strip()
    fence = re.search(r'\{[\s\S]*\}', text)
    if not fence:
        return {}
    try:
        return json.loads(fence.group(0))
    except json.JSONDecodeError as e:
        logger.warning("compare_vehicles JSON decode failed: %s | text=%s", e, text[:200])
        return {}


def compare_vehicles(image_path_a: str, image_path_b: str, prompt_text: str = None) -> Optional[dict]:
    """使用 MaaS qwen2.5-vl-72b 同时看两张图片，判断两辆车是否同一辆。

    Args:
        image_path_a: 图 A 路径（建议 jpg/png）
        image_path_b: 图 B 路径
        prompt_text: 自定义 prompt；默认使用 ``compare_vehicles_prompt``

    Returns:
        dict 形如 ``{"is_same_vehicle": bool, "confidence": float, "reason": str}``；
        任何失败（缺 api_key / 文件读失败 / HTTP 异常 / JSON 解析失败）返回 ``None``。
    """
    from apps.api.core.config import MAAS_API_KEY, MAAS_MODEL, MAAS_API_URL, LLM_TIMEOUT

    if not MAAS_API_KEY:
        logger.warning("compare_vehicles: MAAS_API_KEY not configured")
        return None

    if not image_path_a or not image_path_b:
        logger.warning("compare_vehicles: missing image path (a=%s b=%s)", image_path_a, image_path_b)
        return None

    try:
        b64_a = _encode_image(image_path_a)
        b64_b = _encode_image(image_path_b)
    except Exception as e:
        logger.error("compare_vehicles: image read failed (%s, %s): %s", image_path_a, image_path_b, e)
        return None

    payload = {
        "model": MAAS_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text or compare_vehicles_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{_mime_for_path(image_path_a)};base64,{b64_a}"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{_mime_for_path(image_path_b)};base64,{b64_b}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }

    try:
        response = requests.post(
            MAAS_API_URL,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MAAS_API_KEY}',
            },
            data=json.dumps(payload),
            timeout=LLM_TIMEOUT,
        )
        result = response.json()
    except Exception as e:
        logger.error("compare_vehicles: HTTP/JSON error: %s", e)
        return None

    if 'choices' not in result or not result['choices']:
        logger.warning("compare_vehicles: API response missing choices: %s", result)
        return None

    content = result['choices'][0].get('message', {}).get('content', '')
    parsed = _parse_compare_payload(content)
    if not parsed:
        logger.warning("compare_vehicles: empty/invalid JSON in response: %s", content[:200])
        return None

    is_same = parsed.get('is_same_vehicle')
    if not isinstance(is_same, bool):
        coerced = str(is_same).strip().lower()
        if coerced in ('true', '1', 'yes'):
            is_same = True
        elif coerced in ('false', '0', 'no'):
            is_same = False
        else:
            logger.warning("compare_vehicles: is_same_vehicle not bool: %r", is_same)
            return None

    try:
        confidence = float(parsed.get('confidence', 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = parsed.get('reason') or ''

    return {
        'is_same_vehicle': is_same,
        'confidence': confidence,
        'reason': str(reason),
        'model': MAAS_MODEL,
    }
