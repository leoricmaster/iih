"""内容可信度公式单元测试（doc-04 §2.1）。

参数化覆盖所有公式分支：反证未证伪→5、N≥2→1、N=1 R∈{A,B}→2、
N=1 R=C→3、N=1 R∈{D,E}→4、N=1 R=F→6（落入完成评估但证据不足）。
"""

import pytest

from iih.ledger.formula import (
    CONTENT_CREDIBILITY_FORMULA_VERSION,
    assemble_rating,
    compute_content_credibility,
)


def test_formula_version_is_stable() -> None:
    """公式版本号记入推理记录，修订不回溯历史（doc-04 §2 开篇）。"""
    assert CONTENT_CREDIBILITY_FORMULA_VERSION == "content_credibility_v1"


@pytest.mark.parametrize(
    ("n", "r", "expected"),
    [
        (1, "A", 2),
        (1, "B", 2),
        (1, "C", 3),
        (1, "D", 4),
        (1, "E", 4),
        (1, "F", 6),  # 完成评估但证据不足（含 R = F）
        (2, "A", 1),
        (2, "B", 1),
        (3, "C", 1),
        (5, "F", 1),
    ],
)
def test_compute_content_credibility_matches_formula_table(n: int, r: str, expected: int) -> None:
    """doc-04 §2.1 公式表自上而下首个命中。"""
    assert compute_content_credibility(n, r) == expected


def test_compute_content_credibility_unrefuted_contradiction_returns_5() -> None:
    """有反证但未证伪 → 5（本里程碑 Verifier 不检测，恒为 False；分支位保留）。"""
    assert compute_content_credibility(1, "A", has_unrefuted_contradiction=True) == 5
    assert compute_content_credibility(3, "B", has_unrefuted_contradiction=True) == 5


def test_compute_content_credibility_rejects_invalid_reliability() -> None:
    """非法信源可靠度档（非 A–F）抛 ValueError。"""
    with pytest.raises(ValueError, match="非法信源可靠度档"):
        compute_content_credibility(1, "X")
    with pytest.raises(ValueError, match="非法信源可靠度档"):
        compute_content_credibility(1, "")


def test_compute_content_credibility_zero_sources_falls_to_6() -> None:
    """N=0 防御性兜底：完成评估但证据不足（不应出现于候选条目）。"""
    assert compute_content_credibility(0, "A") == 6


@pytest.mark.parametrize(
    ("r", "credibility", "expected"),
    [
        ("A", 1, "A1"),
        ("B", 2, "B2"),
        ("C", 3, "C3"),
        ("D", 4, "D4"),
        ("E", 5, "E5"),
        ("F", 6, "F6"),
    ],
)
def test_assemble_rating_combines_reliability_and_credibility(
    r: str, credibility: int, expected: str
) -> None:
    """二维评级 = 信源可靠度 + 内容可信度（doc-02 §5）。"""
    assert assemble_rating(r, credibility) == expected


def test_assemble_rating_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="非法信源可靠度档"):
        assemble_rating("X", 2)
    with pytest.raises(ValueError, match="非法内容可信度"):
        assemble_rating("B", 0)
    with pytest.raises(ValueError, match="非法内容可信度"):
        assemble_rating("B", 7)
