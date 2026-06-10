"""图片下载公共工具"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Iterable, Dict
from io import BytesIO

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from apps.api.core.config import IMAGE_DOWNLOAD_TIMEOUT, IMAGE_DOWNLOAD_RETRIES
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


def _is_image_response(response) -> bool:
    return response.status_code == 200 and 'image' in response.headers.get('Content-Type', '')


def _proxies_for(url: str):
    if url.startswith('http://10.') or url.startswith('https://10.'):
        return {'http': None, 'https': None}
    return None


def _attempt_once(url: str, timeout: int):
    proxies = _proxies_for(url)
    return requests.get(url, timeout=timeout, proxies=proxies)


def download_image(url: str, timeout: int = None) -> Optional[BytesIO]:
    """下载图片，返回 BytesIO 对象。

    使用 ``IMAGE_DOWNLOAD_RETRIES`` (默认 3) 次数进行指数退避重试。
    任何 ``requests.RequestException`` 或响应非 image/* 都触发重试。
    """
    if not HAS_REQUESTS:
        return None
    if not url:
        return None

    if timeout is None:
        timeout = IMAGE_DOWNLOAD_TIMEOUT
    retries = max(1, IMAGE_DOWNLOAD_RETRIES)

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            response = _attempt_once(url, timeout)
            if _is_image_response(response):
                return BytesIO(response.content)
            last_exc = ValueError(
                f"non-image response: status={response.status_code} "
                f"content-type={response.headers.get('Content-Type', '')}"
            )
        except requests.RequestException as e:
            last_exc = e
        except Exception as e:
            last_exc = e

        if attempt < retries:
            backoff = 2 ** (attempt - 1)
            logger.warning(
                "download_image retry %d/%d for %s: %s (sleep %ds)",
                attempt, retries, url, last_exc, backoff,
            )
            time.sleep(backoff)

    logger.warning("Failed to download image from %s after %d attempts: %s", url, retries, last_exc)
    return None


def download_images_parallel(
    urls: Iterable[str],
    max_workers: int = 2,
) -> Dict[str, Optional[BytesIO]]:
    """并行下载多张图片，返回 ``{url: BytesIO|None}``。

    失败/超时的 URL 对应值为 ``None``，不会抛异常。
    """
    url_list = [u for u in urls if u]
    if not url_list:
        return {}

    results: Dict[str, Optional[BytesIO]] = {u: None for u in url_list}
    if not HAS_REQUESTS:
        return results

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        future_to_url = {pool.submit(download_image, u): u for u in url_list}
        for future, url in future_to_url.items():
            try:
                results[url] = future.result()
            except Exception as e:
                logger.warning("download_images_parallel failed for %s: %s", url, e)
                results[url] = None
    return results
