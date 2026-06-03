"""图片下载公共工具"""

from typing import Optional
from io import BytesIO

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from apps.api.core.config import IMAGE_DOWNLOAD_TIMEOUT
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


def download_image(url: str, timeout: int = None) -> Optional[BytesIO]:
    """下载图片，返回 BytesIO 对象"""
    if not HAS_REQUESTS:
        return None

    if timeout is None:
        timeout = IMAGE_DOWNLOAD_TIMEOUT

    proxies = None
    if url.startswith('http://10.') or url.startswith('https://10.'):
        proxies = {'http': None, 'https': None}

    try:
        response = requests.get(url, timeout=timeout, proxies=proxies)
        if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
            return BytesIO(response.content)
    except Exception as e:
        logger.warning("Failed to download image from %s: %s", url, e)
    return None
