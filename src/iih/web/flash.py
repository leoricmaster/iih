"""Flash 提示：成功反馈经查询参数回传页面（与 err 同款无会话方案）。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi.responses import RedirectResponse


def redirect_with_flash(url: str, message: str, *, param: str = "flash") -> RedirectResponse:
    """303 跳回目标页并携带提示；清掉目标上既有 flash/err，避免陈旧提示残留。"""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in (param, "err")]
    query.append((param, message))
    target = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return RedirectResponse(target, status_code=303)
