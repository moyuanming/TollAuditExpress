import os
import base64
import requests
import json

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
from LLM.Prompt import prompt
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

def detect_truck_Ollama(image_path):
    """
    使用 llava 模型检测图片是否为货车

    Args:
        image_path (str): 图片文件的完整路径

    Returns:
        int or None:
            1: 是货车
            0: 不是货车
            None: 检测失败
    """
    try:
        # 读取并编码图片
        with open(image_path, "rb") as image_file:
            base64_data = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error("图片读取失败: %s", e)
        return None

    # 构建请求数据
    payload = {
        "model": "gemma3:27b",
        "prompt": prompt,
        "images": [base64_data]
    }

    try:
        # 发送请求到本地Ollama服务
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        # 检查响应状态
        response.raise_for_status()

        # 解析响应
        response_text = ""
        for line in response.text.strip().split('\n'):
            if line:
                try:
                    json_response = json.loads(line)
                    if 'response' in json_response:
                        response_text += json_response['response']
                except json.JSONDecodeError:
                    continue

        # 分析结果
        response_text = response_text.strip()
        if '1' in response_text:
            return 1
        elif '0' in response_text:
            return 0
        else:
            logger.warning("无法解析响应 %s: %s", image_path, response_text)
            return None

    except Exception as e:
        logger.error("API请求失败 %s: %s", image_path, e)
        return None

# 测试代码
if __name__ == "__main__":
    # 测试单张图片
    test_image = "data/test/川AFY2668_4_5104234202080646_G057565002001010100302025040510103296_015104235823432002115520250405102732_license.jpg"
    result = detect_truck_Ollama(test_image)
    if result == 1:
        print("这是货车")
    elif result == 0:
        print("这不是货车")
    else:
        print("检测失败")
