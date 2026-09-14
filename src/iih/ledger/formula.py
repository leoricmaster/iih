"""情报评级公式（doc-04 §2）：确定性映射，公式版本记入推理记录。

变量由对应智能体测量（decision-01）：核实智能体测 N（独立信源数）与 R（出处信源可靠度），
本模块出内容可信度 1–6。数值相对易变，故入数据设计不入 decision——调整数值不算架构变更。
"""

CONTENT_CREDIBILITY_FORMULA_VERSION = "content_credibility_v1"

RELIABILITY_GRADES = frozenset({"A", "B", "C", "D", "E", "F"})


def compute_content_credibility(
    n: int, r: str, *, has_unrefuted_contradiction: bool = False
) -> int:
    """按 doc-04 §2.1 公式（自上而下首个命中）计算内容可信度 1–6。

    变量：
    - n：独立信源计数（穿透转引链后）
    - r：出处信源可靠度档（A–F）
    - has_unrefuted_contradiction：有反证但未证伪（本里程碑暂不检测，恒为 False）

    公式版本：CONTENT_CREDIBILITY_FORMULA_VERSION
    """
    if r not in RELIABILITY_GRADES:
        raise ValueError(f"非法信源可靠度档：{r}（须为 A–F）")

    if has_unrefuted_contradiction:
        return 5  # 有反证但未证伪（doc-04 §2.1 第 1 条）
    if n >= 2:
        return 1
    if n == 1:
        if r in {"A", "B"}:
            return 2
        if r == "C":
            return 3
        if r in {"D", "E"}:
            return 4
    # 完成评估但证据不足（含 R = F；n <= 0 防御性兜底）
    return 6


def assemble_rating(r: str, credibility: int) -> str:
    """组装二维评级（doc-02 §5）：信源可靠度 A–F + 内容可信度 1–6，如 "B2"。"""
    if r not in RELIABILITY_GRADES:
        raise ValueError(f"非法信源可靠度档：{r}（须为 A–F）")
    if not 1 <= credibility <= 6:
        raise ValueError(f"非法内容可信度：{credibility}（须为 1–6）")
    return f"{r}{credibility}"
