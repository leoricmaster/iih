"""状态机执行器（技术架构 §4）：接收提案 → 校验 → 执行状态迁移 → 落账。

校验含字段完整、状态前置、溯源必填；唯一写账入口；失败驳回、状态不变；
提案即事务单元，落账原子；无溯源不落账由校验强制。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import (
    IntelligenceItem,
    ItemStatus,
    Medium,
    Modality,
    Outlet,
    Source,
)
from iih.ledger.proposal import (
    IntelligenceItemNewProposal,
    Proposal,
    ProvenanceData,
)


class ProposalRejectedError(Exception):
    """提案驳回：校验未通过，状态不变。"""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("；".join(reasons))


@dataclass(frozen=True)
class ExecutionResult:
    """落账结果。"""

    item_id: int


class StateMachineExecutor:
    """接收提案并落账。每类提案一个处理器；提案即事务单元。"""

    def execute(self, proposal: Proposal, session: Session) -> ExecutionResult:
        match proposal:
            case IntelligenceItemNewProposal():
                return self._execute_item_new(proposal, session)
            case _:
                raise ProposalRejectedError([f"未知提案类型：{type(proposal).__name__}"])

    def _execute_item_new(
        self, proposal: IntelligenceItemNewProposal, session: Session
    ) -> ExecutionResult:
        provenance = proposal.provenance
        reasons = self._validate_completeness(proposal)

        medium: Medium | None = None
        modality: Modality | None = None
        if not reasons:
            medium = session.scalars(
                select(Medium).where(Medium.code == provenance.medium_code)
            ).first()
            modality = session.scalars(
                select(Modality).where(Modality.code == provenance.modality_code)
            ).first()
            if medium is None:
                reasons.append(f"媒介引用不可解析：{provenance.medium_code}")
            if modality is None:
                reasons.append(f"载体引用不可解析：{provenance.modality_code}")
        if medium is None or modality is None:
            raise ProposalRejectedError(reasons)

        source = self._resolve_source(session, provenance)
        outlet = (
            self._resolve_outlet(session, provenance, source, medium)
            if provenance.outlet_name
            else None
        )
        item = IntelligenceItem(
            statement=proposal.payload.statement,
            status=ItemStatus.LEAD,  # 状态前置 [*] → 线索（doc-02 §4.3）
            mode=proposal.payload.mode,
            medium=medium,
            modality=modality,
            collected_at=provenance.collected_at,
            original_snapshot=provenance.original_snapshot,
            source=source,
            outlet=outlet,
            event_time=proposal.payload.event_time,
        )
        session.add(item)
        session.flush()
        item_id = item.id
        session.commit()  # 提案 = 事务单元：校验、迁移、落账原子提交
        return ExecutionResult(item_id=item_id)

    def _validate_completeness(self, proposal: IntelligenceItemNewProposal) -> list[str]:
        """字段完整性 + 溯源必填（五要素），驳回原因逐条收集。"""
        reasons: list[str] = []
        provenance = proposal.provenance
        if not proposal.payload.statement.strip():
            reasons.append("陈述内容缺失")
        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        if not provenance.modality_code.strip():
            reasons.append("溯源缺失：载体")
        if not provenance.medium_code.strip():
            reasons.append("溯源缺失：媒介")
        if not provenance.original_snapshot.strip():
            reasons.append("溯源缺失：原文快照")
        if not provenance.source_name.strip():
            reasons.append("溯源缺失：信源归因")
        return reasons

    def _resolve_source(self, session: Session, provenance: ProvenanceData) -> Source:
        """信源按名解析；新信源记待确认，不入正式池、不参与信用（decision-05）。"""
        source = session.scalars(
            select(Source).where(Source.name == provenance.source_name)
        ).first()
        if source is None:
            source = Source(
                name=provenance.source_name, type=provenance.source_type, confirmed=False
            )
            session.add(source)
        return source

    def _resolve_outlet(
        self, session: Session, provenance: ProvenanceData, source: Source, medium: Medium
    ) -> Outlet:
        """途径按（信源, 名称）解析，归属唯一信源。"""
        outlet = session.scalars(
            select(Outlet).where(
                Outlet.source_id == source.id, Outlet.name == provenance.outlet_name
            )
        ).first()
        if outlet is None:
            outlet = Outlet(source=source, name=provenance.outlet_name, medium=medium)
            session.add(outlet)
        return outlet
