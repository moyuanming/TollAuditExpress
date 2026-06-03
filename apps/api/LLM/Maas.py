import base64
import json
import requests
from apps.api.LLM.Prompt import prompt
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
