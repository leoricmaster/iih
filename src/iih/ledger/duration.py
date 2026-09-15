"""时长字符串解析（IIH-03.01）：把 "1h"/"24h"/"7d"/"1w"/"30m" 等文本解析为秒数。

供 Director 调度频率过滤、Reviewer 事件时效否决、状态机字段校验共用。
不支持中文格式（如「一周内」）——placeholder 引导用户按 Nh/Nd/Nw/Nm 输入。
"""

import re

_DURATION_RE = re.compile(r"^(\d+)\s*([smhdw])$", re.IGNORECASE)

_UNIT_TO_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_duration_to_seconds(text: str | None) -> int | None:
    """解析时长字符串为秒数；空或非法返回 None。

    >>> parse_duration_to_seconds("1h")
    3600
    >>> parse_duration_to_seconds("7d")
    604800
    >>> parse_duration_to_seconds("")
    None
    >>> parse_duration_to_seconds("一周内")
    None
    """
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    match = _DURATION_RE.match(stripped)
    if match is None:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return value * _UNIT_TO_SECONDS[unit]
