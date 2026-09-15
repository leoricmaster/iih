"""HTML 归一化与内容指纹单测（doc-06 §3 前置过滤）。"""

from iih.tools.html_normalize import extract_link_candidates, fingerprint, normalize


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


# ---- 链接候选提取（doc-06 §3 两跳选链输入：URL + 锚文本） ----


def test_extract_link_candidates_absolutizes_and_dedupes() -> None:
    html = (
        '<a href="/news/2026/jv-agreement">合资公告</a>'
        '<a href="/news/2026/jv-agreement">转载同一链接</a>'
        '<a href="https://other.example/report">外部</a>'
        '<a href="javascript:void(0)">非 http</a>'
        '<a href="mailto:a@b.example">邮件</a>'
    )

    candidates = extract_link_candidates(html, base_url="https://w-mining.example/news")

    assert candidates == [
        ("https://w-mining.example/news/2026/jv-agreement", "合资公告"),
        ("https://other.example/report", "外部"),
    ]


def test_extract_link_candidates_respects_limit_and_order() -> None:
    html = "".join(f'<a href="/p/{i}">第{i}条</a>' for i in range(10))

    candidates = extract_link_candidates(html, base_url="https://x.example", limit=3)

    assert candidates == [(f"https://x.example/p/{i}", f"第{i}条") for i in range(3)]


def test_extract_link_candidates_empty_when_no_anchors() -> None:
    assert extract_link_candidates("<p>纯文本</p>", base_url="https://x.example") == []


def test_extract_link_candidates_ranks_articles_above_menus() -> None:
    """预排序：带日期长标题的叶子路径文章链接排前，目录形菜单链接沉底；入口页自身排除。"""
    html = (
        '<a href="/product/zhongka/">三一重卡</a>'
        '<a href="/news/16627.html">中国进出口银行行长到访三一集团开展合作洽谈 2026.07.29</a>'
        '<a href="/news-collection/">新闻资讯</a>'
        '<a href="/news/16639.html">向文波先生担任集团董事长 2026.05.17</a>'
        '<a href="/about/">关于我们</a>'
    )

    candidates = extract_link_candidates(html, base_url="https://x.example/news-collection/")

    assert candidates == [
        (
            "https://x.example/news/16627.html",
            "中国进出口银行行长到访三一集团开展合作洽谈 2026.07.29",
        ),
        ("https://x.example/news/16639.html", "向文波先生担任集团董事长 2026.05.17"),
        ("https://x.example/product/zhongka/", "三一重卡"),
        ("https://x.example/about/", "关于我们"),
    ]
