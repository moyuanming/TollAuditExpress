import base64
from zhipuai import ZhipuAI
from apps.api.LLM.Prompt import prompt
from apps.api.core.config import ZHIPU_API_KEY
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

def detect_truck(image_path):
    """
    检测单张图片是否为货车

    Args:
        image_path (str): 图片文件的完整路径

    Returns:
        int or None:
            1: 是货车
            0: 不是货车
            None: 检测失败
    """
    if not ZHIPU_API_KEY:
        logger.warning("ZHIPU_API_KEY not configured")
        return None

    try:
        with open(image_path, "rb") as image_file:
            base64_data = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error("图片读取失败: %s", e)
        return None


    client = ZhipuAI(api_key=ZHIPU_API_KEY)

    try:
        response = client.chat.completions.create(
            model="glm-4v-plus",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}
                        }
                    ]
                }
            ],
            temperature=0.1,
            top_p=0.1,
            max_tokens=10,
            stream=False
        )
        
        result = response.choices[0].message.content.strip()
        if '1' in result:
            return 1
        elif '0' in result:
            return 0
        else:
            logger.warning("无法解析响应 %s: %s", image_path, result)
            return None
            
    except Exception as e:
        logger.error("API请求失败 %s: %s", image_path, e)
        return None

