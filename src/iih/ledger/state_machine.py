"""状态机执行器（技术架构 §4）：接收提案 → 校验 → 执行状态迁移 → 落账。

校验含字段完整、状态前置、溯源必填；唯一写账入口；失败驳回、状态不变；
提案即事务单元，落账原子；无溯源不落账由校验强制。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    Medium,
    Modality,
    Outlet,
    ProvenanceChainNode,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    VerificationOutcome,
    VerificationRecord,
)
from iih.ledger.proposal import (
    IntelligenceItemNewProposal,
    IntelligenceRequirementActivateProposal,
    IntelligenceRequirementCloseProposal,
    IntelligenceRequirementPauseProposal,
    IntelligenceRequirementRegisterProposal,
    IntelligenceRequirementResumeProposal,
    ItemProvenanceAppendProposal,
    ItemReverifyProposal,
    Proposal,
    ProvenanceData,
    ReviewProposal,
    SourceRegisterProposal,
    VerificationProposal,
)


class ProposalRejectedError(Exception):
    """提案驳回：校验未通过，状态不变。"""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("；".join(reasons))


@dataclass(frozen=True)
class ExecutionResult:
    """落账结果。"""

    item_id: int | None = None
    source_id: int | None = None
    requirement_id: int | None = None


class StateMachineExecutor:
    """接收提案并落账。每类提案一个处理器；提案即事务单元。"""

    def execute(self, proposal: Proposal, session: Session) -> ExecutionResult:
        match proposal:
            case IntelligenceItemNewProposal():
                return self._execute_item_new(proposal, session)
            case SourceRegisterProposal():
                return self._execute_source_register(proposal, session)
            case IntelligenceRequirementRegisterProposal():
                return self._execute_ir_register(proposal, session)
            case IntelligenceRequirementActivateProposal():
                return self._execute_ir_activate(proposal, session)
            case IntelligenceRequirementPauseProposal():
                return self._execute_ir_transition(
                    proposal,
                    session,
                    from_statuses=(IntelligenceRequirementStatus.ACTIVE,),
                    to_status=IntelligenceRequirementStatus.PAUSED,
                )
            case IntelligenceRequirementResumeProposal():
                return self._execute_ir_transition(
                    proposal,
                    session,
                    from_statuses=(IntelligenceRequirementStatus.PAUSED,),
                    to_status=IntelligenceRequirementStatus.ACTIVE,
                )
            case IntelligenceRequirementCloseProposal():
                return self._execute_ir_transition(
                    proposal,
                    session,
                    from_statuses=(
                        IntelligenceRequirementStatus.ACTIVE,
                        IntelligenceRequirementStatus.PAUSED,
                    ),
                    to_status=IntelligenceRequirementStatus.CLOSED,
                )
            case ItemProvenanceAppendProposal():
                return self._execute_item_provenance_append(proposal, session)
            case ReviewProposal():
                return self._execute_review(proposal, session)
            case VerificationProposal():
                return self._execute_verification(proposal, session)
            case ItemReverifyProposal():
                return self._execute_item_reverify(proposal, session)
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

        # AUTOMATED 模式：信源必须已登记（confirmed=True）；MANUAL 模式：归因新建待确认
        if proposal.payload.mode is ItemMode.AUTOMATED:
            source = self._resolve_confirmed_source(session, provenance, reasons)
            if source is None:
                raise ProposalRejectedError(reasons)
            outlet = (
                self._resolve_existing_outlet(session, provenance, source, reasons)
                if provenance.outlet_name
                else None
            )
            if reasons:
                raise ProposalRejectedError(reasons)
        else:
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
            content_fingerprint=proposal.payload.content_fingerprint,
            original_url=proposal.payload.original_url,
        )
        session.add(item)
        session.flush()
        # 初始转引链节点：出处信源即首节点（doc-03 §六）
        node = ProvenanceChainNode(
            item=item,
            source=source,
            outlet=outlet,
            modality=modality,
            medium=medium,
            collected_at=provenance.collected_at,
            original_url=proposal.payload.original_url,
        )
        session.add(node)
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

    def _resolve_confirmed_source(
        self, session: Session, provenance: ProvenanceData, reasons: list[str]
    ) -> Source | None:
        """AUTOMATED 模式：信源必须已登记 confirmed=True（doc-05 双通道确认制边界）。"""
        source = session.scalars(
            select(Source).where(Source.name == provenance.source_name)
        ).first()
        if source is None:
            reasons.append(f"自动拉取信源未登记：{provenance.source_name}")
            return None
        if not source.confirmed:
            reasons.append(f"自动拉取信源未确认：{provenance.source_name}")
            return None
        return source

    def _resolve_existing_outlet(
        self, session: Session, provenance: ProvenanceData, source: Source, reasons: list[str]
    ) -> Outlet | None:
        """AUTOMATED 模式：途径必须已登记，不归因新建。"""
        outlet = session.scalars(
            select(Outlet).where(
                Outlet.source_id == source.id, Outlet.name == provenance.outlet_name
            )
        ).first()
        if outlet is None:
            reasons.append(f"自动拉取途径未登记：{provenance.outlet_name}")
            return None
        return outlet

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

    def _execute_source_register(
        self, proposal: SourceRegisterProposal, session: Session
    ) -> ExecutionResult:
        """种子信源登记（decision-05 通道一）：新主体 + 首条互联网途径。

        校验：字段完整 + medium=internet 解析 + 信源名唯一 + 初始档必填合法（doc-04 §2.3）；
        落账 Source.confirmed=True、credit=initial_credit（人工先验初值）。
        本任务范围仅新建主体；为既有主体补途径留待后续。
        """
        reasons = self._validate_register_completeness(proposal)
        if reasons:
            raise ProposalRejectedError(reasons)

        payload = proposal.payload
        medium = session.scalars(select(Medium).where(Medium.code == "internet")).first()
        if medium is None:
            raise ProposalRejectedError(["媒介引用不可解析：internet"])

        existing = session.scalars(select(Source).where(Source.name == payload.source_name)).first()
        if existing is not None:
            raise ProposalRejectedError([f"信源名已存在：{payload.source_name}"])

        source = Source(
            name=payload.source_name,
            type=payload.source_type,
            confirmed=True,
            credit=payload.initial_credit,
        )
        outlet = Outlet(
            source=source,
            name=payload.outlet_name,
            entry=payload.outlet_entry,
            medium=medium,
        )
        session.add_all([source, outlet])
        session.flush()
        source_id = source.id
        session.commit()
        return ExecutionResult(source_id=source_id)

    def _validate_register_completeness(self, proposal: SourceRegisterProposal) -> list[str]:
        """字段完整性校验：4 字段非空白 + 初始档合法。source_type 已是枚举，无需校验。"""
        reasons: list[str] = []
        payload = proposal.payload
        if not payload.source_name.strip():
            reasons.append("主体名称缺失")
        if not payload.outlet_name.strip():
            reasons.append("途径名缺失")
        if not payload.outlet_entry.strip():
            reasons.append("采集入口缺失")
        if not payload.initial_credit:
            reasons.append("初始信用档缺失：登记必填（A–F）")
        elif payload.initial_credit not in "ABCDEF":
            reasons.append(f"初始信用档不合法：{payload.initial_credit}（需 A–F）")
        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        return reasons

    # ---- IIH-01.08 互联网信源自动拉取 ----

    def _execute_ir_register(
        self, proposal: IntelligenceRequirementRegisterProposal, session: Session
    ) -> ExecutionResult:
        """情报需求登记：[*] → 草稿 Draft（doc-02 §4.1）。

        校验：name + content_spec 非空白 + 依据非空白。
        """
        reasons: list[str] = []
        payload = proposal.payload
        if not payload.name.strip():
            reasons.append("需求名称缺失")
        if not payload.content_spec.strip():
            reasons.append("内容规格缺失")
        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        if reasons:
            raise ProposalRejectedError(reasons)

        ir = IntelligenceRequirement(
            name=payload.name.strip(),
            content_spec=payload.content_spec.strip(),
            status=IntelligenceRequirementStatus.DRAFT,
        )
        session.add(ir)
        session.flush()
        requirement_id = ir.id
        session.commit()
        return ExecutionResult(requirement_id=requirement_id)

    def _execute_ir_activate(
        self, proposal: IntelligenceRequirementActivateProposal, session: Session
    ) -> ExecutionResult:
        """情报需求激活：草稿 Draft → 激活 Active（doc-02 §4.1）。

        前置违反（非 Draft）驳回，状态不变。
        """
        ir = session.get(IntelligenceRequirement, proposal.payload.requirement_id)
        if ir is None:
            raise ProposalRejectedError(["情报需求不存在"])
        if ir.status is not IntelligenceRequirementStatus.DRAFT:
            raise ProposalRejectedError([f"前置违反：当前状态 {ir.status.value}，需 Draft"])

        ir.status = IntelligenceRequirementStatus.ACTIVE
        session.flush()
        requirement_id = ir.id
        session.commit()
        return ExecutionResult(requirement_id=requirement_id)

    def _execute_ir_transition(
        self,
        proposal: (
            IntelligenceRequirementPauseProposal
            | IntelligenceRequirementResumeProposal
            | IntelligenceRequirementCloseProposal
        ),
        session: Session,
        *,
        from_statuses: tuple[IntelligenceRequirementStatus, ...],
        to_status: IntelligenceRequirementStatus,
    ) -> ExecutionResult:
        """情报需求通用迁移：暂停 / 恢复 / 关闭（doc-02 §4.1）。

        前置违反（不在 from_statuses）驳回，状态不变。
        """
        ir = session.get(IntelligenceRequirement, proposal.payload.requirement_id)
        if ir is None:
            raise ProposalRejectedError(["情报需求不存在"])
        if ir.status not in from_statuses:
            allowed = " 或 ".join(s.value for s in from_statuses)
            raise ProposalRejectedError([f"前置违反：当前状态 {ir.status.value}，需 {allowed}"])

        ir.status = to_status
        session.flush()
        requirement_id = ir.id
        session.commit()
        return ExecutionResult(requirement_id=requirement_id)

    def _execute_item_provenance_append(
        self, proposal: ItemProvenanceAppendProposal, session: Session
    ) -> ExecutionResult:
        """转引链节点追加（doc-06 §3 前置过滤命中路径）。

        校验：item 存在 + source 可解析 + 同(item, source, outlet)节点不重复；
        自动拉取场景下 source 应已 confirmed，本提案由 Collector 在指纹命中时产出。
        """
        payload = proposal.payload
        item = session.get(IntelligenceItem, payload.item_id)
        if item is None:
            raise ProposalRejectedError(["情报条目不存在"])

        source = session.scalars(select(Source).where(Source.name == payload.source_name)).first()
        if source is None:
            raise ProposalRejectedError([f"信源不可解析：{payload.source_name}"])

        outlet: Outlet | None = None
        if payload.outlet_name:
            outlet = session.scalars(
                select(Outlet).where(
                    Outlet.source_id == source.id, Outlet.name == payload.outlet_name
                )
            ).first()
            if outlet is None:
                raise ProposalRejectedError([f"途径不可解析：{payload.outlet_name}"])

        existing = session.scalars(
            select(ProvenanceChainNode).where(
                ProvenanceChainNode.item_id == item.id,
                ProvenanceChainNode.source_id == source.id,
                ProvenanceChainNode.outlet_id == (outlet.id if outlet else None),
            )
        ).first()
        if existing is not None:
            raise ProposalRejectedError(["转引链节点已存在"])

        node = ProvenanceChainNode(
            item=item,
            source=source,
            outlet=outlet,
            modality=item.modality,
            medium=item.medium,
            collected_at=payload.collected_at,
            original_url=payload.original_url,
        )
        session.add(node)
        session.flush()
        session.commit()
        return ExecutionResult(item_id=item.id)

    # ---- IIH-01.02 线索审查过滤 ----

    def _execute_review(self, proposal: ReviewProposal, session: Session) -> ExecutionResult:
        """审查决策：Lead → Candidate（PASS）或 Lead → Noise（REJECT）（doc-02 §4.3、doc-06 §4）。

        校验：item 存在 + 当前状态为 LEAD（前置）+ 依据非空 + decision 合法
        + PASS 时 matched_requirement_id 必填且需求存在且状态为 ACTIVE
        + REJECT 时 reason_type 必填。
        落账：状态迁移 + ReviewDecision 记录（依据持久化，满足 doc-08 #8）。
        """
        payload = proposal.payload
        reasons: list[str] = []

        if not proposal.rationale.strip():
            reasons.append("依据缺失")

        item = session.get(IntelligenceItem, payload.item_id)
        if item is None:
            reasons.append("情报条目不存在")
        elif item.status is not ItemStatus.LEAD:
            reasons.append(f"前置违反：当前状态 {item.status.value}，需 Lead")

        matched_requirement: IntelligenceRequirement | None = None
        if payload.decision is ReviewDecisionEnum.PASS:
            if payload.matched_requirement_id is None:
                reasons.append("通过决策缺少匹配的情报需求")
            else:
                matched_requirement = session.get(
                    IntelligenceRequirement, payload.matched_requirement_id
                )
                if matched_requirement is None:
                    reasons.append("匹配的情报需求不存在")
                elif matched_requirement.status is not IntelligenceRequirementStatus.ACTIVE:
                    reasons.append(f"匹配的情报需求非激活态：{matched_requirement.status.value}")
        else:  # REJECT
            if payload.reason_type is None:
                reasons.append("否决决策缺少理由类型")

        if reasons:
            raise ProposalRejectedError(reasons)

        assert item is not None
        if payload.decision is ReviewDecisionEnum.PASS:
            item.status = ItemStatus.CANDIDATE
        else:
            item.status = ItemStatus.NOISE

        decision = ReviewDecision(
            item=item,
            decision=payload.decision,
            reason_type=payload.reason_type,
            matched_requirement=matched_requirement,
            rationale=proposal.rationale,
        )
        session.add(decision)
        session.flush()
        item_id = item.id
        session.commit()
        return ExecutionResult(item_id=item_id)

    # ---- IIH-01.03 核实评级 ----

    def _execute_verification(
        self, proposal: VerificationProposal, session: Session
    ) -> ExecutionResult:
        """核实评级：Candidate → Verified 或 Candidate → Undetermined（doc-02 §4.3、doc-06 §5）。

        校验：item 存在 + 当前状态为 CANDIDATE（前置）+ 依据非空 + outcome 合法
        + VERIFIED 时 N ≥ 1 + R ∈ {A–F} + credibility ∈ {1..6} + rating 非空
        + UNDETERMINED 时 R/credibility/rating 均为空。
        落账：状态迁移 + IntelligenceItem.rating（VERIFIED）+ VerificationRecord 记录
        （依据 + 公式版本 + 变量快照持久化，满足 doc-08 #8 与 doc-04 §1 推理记录）。
        """
        payload = proposal.payload
        reasons: list[str] = []

        if not proposal.rationale.strip():
            reasons.append("依据缺失")

        item = session.get(IntelligenceItem, payload.item_id)
        if item is None:
            reasons.append("情报条目不存在")
        elif item.status is not ItemStatus.CANDIDATE:
            reasons.append(f"前置违反：当前状态 {item.status.value}，需 Candidate")

        reliability_grades = {"A", "B", "C", "D", "E", "F"}
        if payload.outcome is VerificationOutcome.VERIFIED:
            if payload.independent_source_count < 1:
                reasons.append("已核实决策缺少独立信源计数")
            if payload.source_reliability is None:
                reasons.append("已核实决策缺少信源可靠度")
            elif payload.source_reliability not in reliability_grades:
                reasons.append(f"信源可靠度非法：{payload.source_reliability}（须 A–F）")
            if payload.content_credibility is None:
                reasons.append("已核实决策缺少内容可信度")
            elif not 1 <= payload.content_credibility <= 6:
                reasons.append(f"内容可信度非法：{payload.content_credibility}（须 1–6）")
            if not payload.rating:
                reasons.append("已核实决策缺少评级")
        else:  # UNDETERMINED
            if payload.source_reliability is not None:
                reasons.append("存疑决策不应含信源可靠度")
            if payload.content_credibility is not None:
                reasons.append("存疑决策不应含内容可信度")
            if payload.rating is not None:
                reasons.append("存疑决策不应含评级")

        if reasons:
            raise ProposalRejectedError(reasons)

        assert item is not None
        if payload.outcome is VerificationOutcome.VERIFIED:
            item.status = ItemStatus.VERIFIED
            item.rating = payload.rating
        else:
            item.status = ItemStatus.UNDETERMINED

        record = VerificationRecord(
            item=item,
            outcome=payload.outcome,
            independent_source_count=payload.independent_source_count,
            source_reliability=payload.source_reliability,
            content_credibility=payload.content_credibility,
            rating=payload.rating,
            formula_version=proposal.formula_version,
            rationale=proposal.rationale,
        )
        session.add(record)
        session.flush()
        item_id = item.id
        session.commit()
        return ExecutionResult(item_id=item_id)

    def _execute_item_reverify(
        self, proposal: ItemReverifyProposal, session: Session
    ) -> ExecutionResult:
        """存疑重核回流：Undetermined → Candidate（doc-02 §4.1「复核期到 / 新证据」）。

        校验：item 存在 + 当前状态为 UNDETERMINED（前置）+ 依据（新证据说明）非空。
        仅做状态回流，不写核实记录——重评由核实段产出新的 VerificationRecord（版本化历史）。
        """
        reasons: list[str] = []
        if not proposal.rationale.strip():
            reasons.append("依据缺失：重核回流需说明新证据")

        item = session.get(IntelligenceItem, proposal.payload.item_id)
        if item is None:
            reasons.append("情报条目不存在")
        elif item.status is not ItemStatus.UNDETERMINED:
            reasons.append(f"前置违反：当前状态 {item.status.value}，需 Undetermined")

        if reasons:
            raise ProposalRejectedError(reasons)

        assert item is not None
        item.status = ItemStatus.CANDIDATE
        session.flush()
        item_id = item.id
        session.commit()
        return ExecutionResult(item_id=item_id)
