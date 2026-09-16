"""Tavily 搜索客户端（doc-05 §4 工具层「检索」位）：无状态 HTTP 检索，返回结果列表。

按 doc-05 §2 外部系统互联网「池外自由探索」用途：采集智能体 _explore_outside_pool 调用
检索 IR 主题词，取 top-N 结果供 LLM 选链。失败抛 SearchError；调用方决定跳过/重试。
无 session、不入账（计量由调用方在 LLM 步骤记入 LlmCall）。
"""

import httpx


class SearchError(Exception):
    """检索失败：4xx/5xx/超时/网络错误/API key 缺失。"""


_TAVILY_ENDPOINT = "https://api.tavily.com/search"


class SearchResult:
    """单条检索结果（仅保留本系统所需字段）。"""

    def __init__(self, *, url: str, title: str, content: str) -> None:
        self.url = url
        self.title = title
        self.content = content


def search(
    query: str,
    *,
    api_key: str,
    max_results: int = 5,
    timeout: float = 15.0,
) -> list[SearchResult]:
    """Tavily 检索：返回 top-N 结果（URL + 标题 + 内容片段）。

    API key 缺失或检索失败统一抛 SearchError；调用方静默跳过不阻断主任务。
    """
    if not api_key:
        raise SearchError("Tavily API key 未配置")
    if not query.strip():
        raise SearchError("检索词为空")
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                _TAVILY_ENDPOINT,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise SearchError(f"Tavily HTTP {exc.response.status_code}: {query}") from exc
    except httpx.HTTPError as exc:
        raise SearchError(f"Tavily 检索失败 {query}: {exc}") from exc

    results = data.get("results", [])
    return [
        SearchResult(
            url=item.get("url", ""),
            title=item.get("title", ""),
            content=item.get("content", ""),
        )
        for item in results
        if item.get("url")
    ]
