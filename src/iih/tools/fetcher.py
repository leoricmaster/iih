"""fetcher 工具层（doc-05 §4）：无状态 HTTP 抓取单页，返回 HTML 文本。

失败抛 FetcherError；调用方决定重试/跳过。无 session、不入账。
"""

import httpx


class FetcherError(Exception):
    """fetcher 抓取失败：4xx/5xx/超时/网络错误。"""


_USER_AGENT = "iih-collector/0.1 (+https://github.com/anthropics/iih)"


def fetch(url: str, *, timeout: float = 10.0) -> str:
    """GET 单页，返回 HTML 文本。4xx/5xx/超时/网络错误统一抛 FetcherError。"""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        raise FetcherError(f"HTTP {exc.response.status_code}: {url}") from exc
    except httpx.HTTPError as exc:
        raise FetcherError(f"抓取失败 {url}: {exc}") from exc
