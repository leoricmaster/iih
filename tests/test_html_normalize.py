"""HTML 归一化与内容指纹单测（doc-06 §3 前置过滤）。"""

from iih.tools.html_normalize import fingerprint, normalize


def test_normalize_strips_script_and_style() -> None:
    html = """
    <html><body>
      <script>alert('x')</script>
      <style>.x { color: red; }</style>
      <p>W 公司公告：与 Z 集团签署合资协议</p>
    </body></html>
    """
    text = normalize(html)
    assert "alert" not in text
    assert "color" not in text
    assert "W 公司公告：与 Z 集团签署合资协议" in text


def test_normalize_strips_nav_footer_header() -> None:
    html = """
    <html><body>
      <nav>菜单</nav>
      <header>页头</header>
      <main>正文</main>
      <footer>页脚</footer>
    </body></html>
    """
    text = normalize(html)
    assert "菜单" not in text
    assert "页头" not in text
    assert "页脚" not in text
    assert "正文" in text


def test_normalize_collapses_whitespace() -> None:
    html = "<p>第一行\n\n   第二行\t\t第三行</p>"
    assert normalize(html) == "第一行 第二行 第三行"


def test_normalize_trims_leading_trailing_whitespace() -> None:
    html = "<body>  正文  </body>"
    assert normalize(html) == "正文"


def test_fingerprint_is_deterministic() -> None:
    assert fingerprint("W 公司公告") == fingerprint("W 公司公告")


def test_fingerprint_differs_for_different_text() -> None:
    assert fingerprint("W 公司公告") != fingerprint("W 公司年报")


def test_fingerprint_is_64_hex_chars() -> None:
    fp = fingerprint("x")
    assert len(fp) == 64
    int(fp, 16)  # 可解析为 hex
