"""fetcher 单测（doc-05 §4 工具层）：mock httpx，验证成功/失败路径。"""

from unittest.mock import patch

import httpx
import pytest

from iih.tools.fetcher import FetcherError, fetch


def _make_response(status_code: int, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(status_code=status_code, text=text, request=request)


def test_fetch_returns_html_on_200() -> None:
    with patch("iih.tools.fetcher.httpx.Client") as mock_client_cls:
        client = mock_client_cls.return_value.__enter__.return_value
        client.get.return_value = _make_response(200, "<html>W 公司公告</html>")

        html = fetch("https://w-mining.example/news")

    assert html == "<html>W 公司公告</html>"
    client.get.assert_called_once()
    args, kwargs = client.get.call_args
    assert args[0] == "https://w-mining.example/news"
    assert "User-Agent" in kwargs["headers"]


def test_fetch_raises_on_404() -> None:
    with patch("iih.tools.fetcher.httpx.Client") as mock_client_cls:
        client = mock_client_cls.return_value.__enter__.return_value
        client.get.return_value = _make_response(404)

        with pytest.raises(FetcherError, match="HTTP 404"):
            fetch("https://w-mining.example/missing")


def test_fetch_raises_on_timeout() -> None:
    with patch("iih.tools.fetcher.httpx.Client") as mock_client_cls:
        client = mock_client_cls.return_value.__enter__.return_value
        client.get.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(FetcherError, match="抓取失败"):
            fetch("https://w-mining.example/news", timeout=0.01)


def test_fetch_raises_on_connection_error() -> None:
    with patch("iih.tools.fetcher.httpx.Client") as mock_client_cls:
        client = mock_client_cls.return_value.__enter__.return_value
        client.get.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(FetcherError, match="抓取失败"):
            fetch("https://w-mining.example/news")
