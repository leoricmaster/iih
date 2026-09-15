"""HTML 归一化与内容指纹（doc-06 §3 前置过滤）。

剥离 script/style/nav/footer/header 等噪声标签，提取 body 文本，空白归一化；
指纹为归一化文本的 SHA-256 hex digest，pre-LLM 计算。
"""

import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_NOISE_TAGS = ("script", "style", "nav", "footer", "header")
_WHITESPACE_RE = re.compile(r"\s+")
_DATE_IN_TEXT_RE = re.compile(r"20\d{2}\s*[./年-]\s*\d{1,2}")


def normalize(html: str) -> str:
    """HTML → 归一化正文文本：剥离噪声标签，折叠空白。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def fingerprint(text: str) -> str:
    """归一化文本的 SHA-256 hex digest（64 字符）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_link_candidates(html: str, *, base_url: str, limit: int = 60) -> list[tuple[str, str]]:
    """提取页面内绝对化 http(s) 链接候选（URL + 锚文本），供 LLM 选文章页。

    确定性预排序（同分保 DOM 序）：日期锚文本 > 长标题 > 叶子路径——
    导航/栏目链接多为目录形 URL + 短菜单锚文本，文章详情页常见叶子路径
    （如 /news/16627.html）与带日期的长标题；避免 60 条截断后清一色导航链接。
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    seen: set[str] = set()
    scored: list[tuple[tuple[int, int, int], str, str]] = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, str(anchor["href"]).strip())
        if url.startswith(("http://", "https://")) and url not in seen and url != base_url:
            seen.add(url)
            text = _WHITESPACE_RE.sub(" ", anchor.get_text()).strip()
            path = url.partition("://")[2].partition("/")[2]
            leaf = 1 if not path.endswith("/") and path.rsplit("/", 1)[-1] else 0
            long_title = 1 if len(text) >= 12 else 0
            dated = 1 if _DATE_IN_TEXT_RE.search(text) else 0
            scored.append(((dated, long_title, leaf), url, text))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(url, text) for _, url, text in scored[:limit]]
