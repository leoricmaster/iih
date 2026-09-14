"""HTML 归一化与内容指纹（doc-06 §3 前置过滤）。

剥离 script/style/nav/footer/header 等噪声标签，提取 body 文本，空白归一化；
指纹为归一化文本的 SHA-256 hex digest，pre-LLM 计算。
"""

import hashlib
import re

from bs4 import BeautifulSoup

_NOISE_TAGS = ("script", "style", "nav", "footer", "header")
_WHITESPACE_RE = re.compile(r"\s+")


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
