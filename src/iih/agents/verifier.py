"""核实智能体 Verifier（doc-06 §5）· 最简版：确定性评级，不调 LLM。

读候选条目 → 穿透转引链统计独立信源 N → 取信源画像可靠度 R → 按公式（doc-04 §2.1）
出内容可信度 1–6 → 组装二维评级（如 B2）→ 产出评级提案。落账由状态机执行器执行。

变量与结论分离（decision-01）：N、R 为事实查询，公式为确定性映射，公式版本记入提案。
本里程碑最简：单信源简化（N=1），不做反证判定、外部佐证、合并印证（后续加厚）。
不调 LLM、不计量——核实在最简版无 LLM 判断场景，符合成本纪律（doc-06 §1）。
"""

from sqlalchemy.orm import Session

from iih.ledger.formula import (
    CONTENT_CREDIBILITY_FORMULA_VERSION,
    assemble_rating,
    compute_content_credibility,
)
from iih.ledger.models import IntelligenceItem, VerificationOutcome
from iih.ledger.proposal import VerificationPayload, VerificationProposal


class Verifier:
    """核实智能体执行器（判断层）：无状态、输出提案。本里程碑最简版不调 LLM。"""

    AGENT_NAME = "verifier"

    def __init__(self, session: Session) -> None:
        self.session = session

    def verify(self, item: IntelligenceItem) -> VerificationProposal:
        """对一条 Candidate 态条目产出核实评级提案。

        流程：
        1. 统计独立信源 N = 转引链节点中 distinct source_id 数量
        2. 取 R = item.source.credit（出处信源画像当前值）
        3. R 为 None → 产出 UNDETERMINED 提案（信源画像未设信用档，无法评定）
        4. R 有值 → 按公式算 content_credibility → 组装 rating → 产出 VERIFIED 提案
        """
        independent_sources = {node.source_id for node in item.provenance_nodes}
        n = len(independent_sources)

        source = item.source
        r = source.credit if source is not None else None

        if r is None:
            return VerificationProposal(
                payload=VerificationPayload(
                    item_id=item.id,
                    outcome=VerificationOutcome.UNDETERMINED,
                    independent_source_count=n,
                    source_reliability=None,
                    content_credibility=None,
                    rating=None,
                ),
                rationale="信源画像未设信用档，无法评定内容可信度",
                formula_version=None,
            )

        credibility = compute_content_credibility(n, r)
        rating = assemble_rating(r, credibility)
        return VerificationProposal(
            payload=VerificationPayload(
                item_id=item.id,
                outcome=VerificationOutcome.VERIFIED,
                independent_source_count=n,
                source_reliability=r,
                content_credibility=credibility,
                rating=rating,
            ),
            rationale=(
                f"穿透转引链得独立信源 N={n}，出处信源可靠度 R={r}，"
                f"公式出内容可信度 {credibility}，组装评级 {rating}"
            ),
            formula_version=CONTENT_CREDIBILITY_FORMULA_VERSION,
        )
