"""状态机执行器（技术架构 §4）：接收提案 → 校验 → 执行状态迁移 → 落账。

校验含字段完整、状态前置、溯源必填；唯一写账入口；失败驳回、状态不变；
提案即事务单元，落账原子；无溯源不落账由校验强制。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.duration import parse_duration_to_seconds
from iih.ledger.models import (
    Derivation,
    Entry,
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    Material,
    Medium,
    Modality,
    ProvenanceChainNode,
    ReviewDecision,
    ReviewDecisionEnum,
    Source,
    SourceAlias,
    SourceRejection,
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
    ItemReviewDisputeProposal,
    Proposal,
    ProvenanceData,
    ReviewProposal,
    SourceConfirmProposal,
    SourceRejectProposal,
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
            case SourceConfirmProposal():
                return self._execute_source_confirm(proposal, session)
            case SourceRejectProposal():
                return self._execute_source_reject(proposal, session)
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
            case ItemReviewDisputeProposal():
                return self._execute_item_review_dispute(proposal, session)
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

        # 归因统一解析（IIH-06.01 通路反转）：按名/别名归入，未知名建待确认信源
        source = self._resolve_source(
            session, provenance, discovered_entry=proposal.payload.original_url
        )

        if proposal.payload.content_fingerprint:
            duplicate = session.scalars(
                select(IntelligenceItem.id).where(
                    IntelligenceItem.content_fingerprint == proposal.payload.content_fingerprint
                )
            ).first()
            if duplicate is not None:
                raise ProposalRejectedError([f"陈述与既有条目 #{duplicate} 内容重复，未重复落账"])

        material: Material | None = None
        derivation: Derivation | None = None
        if proposal.payload.material_id is not None:
            material = session.get(Material, proposal.payload.material_id)
            if material is None:
                raise ProposalRejectedError(["素材引用不可解析"])
            derivation = session.get(Derivation, proposal.payload.derivation_id)
            if derivation is None or derivation.material_id != material.id:
                raise ProposalRejectedError(["派生级引用不可解析或不属于该素材"])

        item = IntelligenceItem(
            statement=proposal.payload.statement,
            status=ItemStatus.LEAD,  # 状态前置 [*] → 线索（doc-02 §4.3）
            mode=proposal.payload.mode,
            medium=medium,
            modality=modality,
            collected_at=provenance.collected_at,
            original_snapshot=provenance.original_snapshot,
            source=source,
            event_time=proposal.payload.event_time,
            content_fingerprint=proposal.payload.content_fingerprint,
            original_url=proposal.payload.original_url,
            snapshot_object_key=proposal.payload.snapshot_object_key,
            material=material,
            derivation=derivation,
        )
        session.add(item)
        session.flush()
        # 初始转引链节点：出处信源即首节点（doc-03 §六）
        node = ProvenanceChainNode(
            item=item,
            source=source,
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
        if proposal.payload.mode is ItemMode.MANUAL and not (
            (provenance.original_snapshot or "").strip()
            or (proposal.payload.material_id and proposal.payload.derivation_id)
        ):
            reasons.append("溯源缺失：原文快照")
        if (
            proposal.payload.mode is ItemMode.AUTOMATED
            and not (proposal.payload.snapshot_object_key or "").strip()
        ):
            reasons.append("溯源缺失：原文快照对象")
        if not provenance.source_name.strip():
            reasons.append("溯源缺失：信源归因")
        return reasons

    def _resolve_source(
        self, session: Session, provenance: ProvenanceData, *, discovered_entry: str | None = None
    ) -> Source:
        """信源按名/别名解析（别名归到归属信源）；新信源记待确认（decision-05）。

        新信源携带发现来源 URL（自动条目的原文链接）时落账 discovered_entry，
        确认时预填建采集入口。已拒绝信源再次被归因命中即重捞：清 rejected_at
        重新入队（拒绝历史由事件表带上）。
        """
        source = self._source_by_name_or_alias(session, provenance.source_name)
        if source is None:
            source = Source(
                name=provenance.source_name,
                type=provenance.source_type,
                confirmed=False,
                discovered_entry=(discovered_entry or "").strip() or None,
            )
            session.add(source)
        elif source.rejected_at is not None:
            source.rejected_at = None
        return source

    def _source_by_name_or_alias(self, session: Session, name: str) -> Source | None:
        """按名解析信源：先正名后别名。别名仅记在已确认信源上，命中即归入，不建待确认行。"""
        source = session.scalars(select(Source).where(Source.name == name)).first()
        if source is not None:
            return source
        alias = session.scalars(select(SourceAlias).where(SourceAlias.name == name)).first()
        return alias.source if alias is not None else None

    # ---- IIH-05.01 待确认信源确认闭环 ----

    def _execute_source_confirm(
        self, proposal: SourceConfirmProposal, session: Session
    ) -> ExecutionResult:
        """待确认信源确认入池（decision-05 准入把关）：待确认 → 已确认。

        校验：信源存在 + confirmed=False 前置 + 初始档必填合法（doc-04 §2.3 解死锁）+ 依据非空
        + 修正名非空白 + 目标名不撞别名。
        三分支：未改名 → 直接入池；改名未撞名 → 以新名入池；撞既有已确认
        信源名 → 并入该信源（条目/转引链节点迁移），待确认行删除，
        信用档沿用目标信源。类型仅在非并入路径修正。
        改名/并入不再自动留档旧名为别名（IIH-06.02：旧名往往是采集智能体产出的脏名）；
        别名改由用户在信源画像页主动声明。
        采集入口（IIH-05.02 补救、IIH-06.03 途径退役）：entry 非空则建采集入口（并入路径
        建到目标信源），留空不建——入池即可被采集，与人工登记同构。
        """
        payload = proposal.payload
        reasons: list[str] = []

        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        source = session.get(Source, payload.source_id)
        if source is None:
            reasons.append("信源不存在")
        elif source.confirmed:
            reasons.append(f"前置违反：信源已确认：{source.name}")
        if not payload.initial_credit:
            reasons.append("初始信用档缺失：确认必设（A–F）")
        elif payload.initial_credit not in "ABCDEF":
            reasons.append(f"初始信用档不合法：{payload.initial_credit}（需 A–F）")
        provided_name = (payload.name or "").strip()
        target_name = provided_name or (source.name if source else "")
        if not target_name:
            reasons.append("信源名缺失")
        if reasons:
            raise ProposalRejectedError(reasons)

        assert source is not None
        existing = session.scalars(
            select(Source).where(Source.name == target_name, Source.id != source.id)
        ).first()
        if existing is not None:
            if not existing.confirmed:
                raise ProposalRejectedError(
                    [f"信源名已存在（待确认）：{target_name}——先处理该信源"]
                )
            return self._merge_into_confirmed(
                session,
                pending=source,
                target=existing,
                entry=payload.entry,
            )
        alias_hit = session.scalars(
            select(SourceAlias).where(SourceAlias.name == target_name)
        ).first()
        if alias_hit is not None:
            raise ProposalRejectedError(
                [f"信源名已存在（别名，归属 {alias_hit.source.name}）：{target_name}"]
            )

        source.name = target_name
        source.confirmed = True
        source.credit = payload.initial_credit
        source.rejected_at = None
        if payload.source_type is not None:
            source.type = payload.source_type
        entry = (payload.entry or "").strip()
        if entry:
            self._ensure_entry(session, source=source, entry=entry)
        session.flush()
        source_id = source.id
        session.commit()
        return ExecutionResult(source_id=source_id)

    def _merge_into_confirmed(
        self,
        session: Session,
        *,
        pending: Source,
        target: Source,
        entry: str | None = None,
    ) -> ExecutionResult:
        """待确认信源并入既有已确认信源：条目/转引链节点迁移，待确认行删除。

        待确认信源无采集入口（入口仅建在已确认信源上）；确认携带采集入口时建到目标
        信源（IIH-05.02 补救），已存在同入口则跳过。信用档沿用目标信源。
        """
        entry_value = (entry or "").strip()
        if entry_value:
            self._ensure_entry(session, source=target, entry=entry_value)
        nodes = session.scalars(
            select(ProvenanceChainNode).where(ProvenanceChainNode.source_id == pending.id)
        ).all()
        for node in nodes:
            node.source = target
        items = session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.source_id == pending.id)
        ).all()
        for item in items:
            item.source = target
        session.delete(pending)
        session.flush()
        target_id = target.id
        session.commit()
        return ExecutionResult(source_id=target_id)

    def _ensure_entry(self, session: Session, *, source: Source, entry: str) -> None:
        """确认时建采集入口（IIH-05.02 补救、IIH-06.03 途径退役）：同主体同入口已存在则跳过。"""
        if any(e.entry == entry for e in source.entries):
            return
        session.add(Entry(source=source, entry=entry))

    def _execute_source_reject(
        self, proposal: SourceRejectProposal, session: Session
    ) -> ExecutionResult:
        """待确认信源拒绝（decision-05）：不入池、留痕出队，confirmed 保持 False。

        前置：信源存在 + confirmed=False。拒绝即出待确认队列（事件表留痕）；
        再次归因命中同名信源时重捞入队（rejected_at 清空），仍可确认。
        已归因条目不受影响（仍指向该信源，不参与记账由 confirmed 边界保持）。
        """
        reasons: list[str] = []
        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        source = session.get(Source, proposal.payload.source_id)
        if source is None:
            reasons.append("信源不存在")
        elif source.confirmed:
            reasons.append(f"前置违反：信源已确认：{source.name}")
        if reasons:
            raise ProposalRejectedError(reasons)

        assert source is not None
        source.rejected_at = datetime.now(UTC)
        session.add(SourceRejection(source=source))
        session.flush()
        source_id = source.id
        session.commit()
        return ExecutionResult(source_id=source_id)

    # ---- IIH-01.08 互联网信源自动拉取 ----

    def _execute_ir_register(
        self, proposal: IntelligenceRequirementRegisterProposal, session: Session
    ) -> ExecutionResult:
        """情报需求登记：[*] → 草稿 Draft（doc-02 §4.1）。

        校验：name + content_spec 非空白 + 依据非空白
        + 频率/时效格式可解析（非空时）
        + valid_until 不早于 valid_from（两者都非空时）
        + source_ids 中每个信源存在且 confirmed=True（decision-05 边界）。
        """
        reasons: list[str] = []
        payload = proposal.payload
        if not payload.name.strip():
            reasons.append("需求名称缺失")
        if not payload.content_spec.strip():
            reasons.append("内容规格缺失")
        if not proposal.rationale.strip():
            reasons.append("依据缺失")
        if payload.collection_frequency and payload.collection_frequency.strip():
            if parse_duration_to_seconds(payload.collection_frequency) is None:
                reasons.append(
                    f"采集频率格式非法：{payload.collection_frequency}（须 Nh/Nd/Nw/Nm）"
                )
        if payload.event_freshness and payload.event_freshness.strip():
            if parse_duration_to_seconds(payload.event_freshness) is None:
                reasons.append(f"事件时效格式非法：{payload.event_freshness}（须 Nh/Nd/Nw/Nm）")
        if payload.valid_from and payload.valid_until and payload.valid_until < payload.valid_from:
            reasons.append("生效窗口结束日早于起始日")
        bound_sources: list[Source] = []
        if payload.source_ids:
            for sid in payload.source_ids:
                src = session.get(Source, sid)
                if src is None:
                    reasons.append(f"信源不存在：{sid}")
                elif not src.confirmed:
                    reasons.append(f"信源未确认，不可绑定：{src.name}")
                else:
                    bound_sources.append(src)
        if reasons:
            raise ProposalRejectedError(reasons)

        ir = IntelligenceRequirement(
            name=payload.name.strip(),
            content_spec=payload.content_spec.strip(),
            status=IntelligenceRequirementStatus.DRAFT,
            collection_frequency=payload.collection_frequency.strip()
            if payload.collection_frequency and payload.collection_frequency.strip()
            else None,
            event_freshness=payload.event_freshness.strip()
            if payload.event_freshness and payload.event_freshness.strip()
            else None,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )
        if bound_sources:
            ir.sources = bound_sources
        session.add(ir)
        session.flush()
        requirement_id = ir.id
        session.commit()
        return ExecutionResult(requirement_id=requirement_id)

    def _execute_ir_activate(
        self, proposal: IntelligenceRequirementActivateProposal, session: Session
    ) -> ExecutionResult:
        """情报需求激活：Draft → Active，或 Closed → Active（重开，doc-02 §4.1）。

        前置违反（非 Draft 且非 Closed）驳回，状态不变。
        """
        ir = session.get(IntelligenceRequirement, proposal.payload.requirement_id)
        if ir is None:
            raise ProposalRejectedError(["情报需求不存在"])
        if ir.status not in (
            IntelligenceRequirementStatus.DRAFT,
            IntelligenceRequirementStatus.CLOSED,
        ):
            raise ProposalRejectedError(
                [f"前置违反：当前状态 {ir.status.value}，需 Draft 或 Closed"]
            )

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

        校验：item 存在 + source 可解析 + 同(item, source)节点不重复；
        自动拉取场景下 source 应已 confirmed，本提案由 Collector 在指纹命中时产出。
        """
        payload = proposal.payload
        item = session.get(IntelligenceItem, payload.item_id)
        if item is None:
            raise ProposalRejectedError(["情报条目不存在"])

        source = session.scalars(select(Source).where(Source.name == payload.source_name)).first()
        if source is None:
            raise ProposalRejectedError([f"信源不可解析：{payload.source_name}"])

        existing = session.scalars(
            select(ProvenanceChainNode).where(
                ProvenanceChainNode.item_id == item.id,
                ProvenanceChainNode.source_id == source.id,
            )
        ).first()
        if existing is not None:
            raise ProposalRejectedError(["转引链节点已存在"])

        node = ProvenanceChainNode(
            item=item,
            source=source,
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

    def _execute_item_review_dispute(
        self, proposal: ItemReviewDisputeProposal, session: Session
    ) -> ExecutionResult:
        """审查异议重审：Noise → Candidate（重审通过）或维持 Noise（doc-02 §4.3、§6）。

        校验：item 存在 + 当前状态为 NOISE（前置）+ 依据非空 + 决策合法
        （通过需 matched_requirement_id 且需求激活；维持否决需 reason_type）。
        落账：状态迁移 + ReviewDecision 记录（重审历史，版本化留痕）。
        """
        payload = proposal.payload
        reasons: list[str] = []

        if not proposal.rationale.strip():
            reasons.append("依据缺失：异议重审需附审查依据")

        item = session.get(IntelligenceItem, payload.item_id)
        if item is None:
            reasons.append("情报条目不存在")
        elif item.status is not ItemStatus.NOISE:
            reasons.append(f"前置违反：当前状态 {item.status.value}，需 Noise")

        matched_requirement: IntelligenceRequirement | None = None
        if payload.decision is ReviewDecisionEnum.PASS:
            if payload.matched_requirement_id is None:
                reasons.append("重审通过缺少匹配的情报需求")
            else:
                matched_requirement = session.get(
                    IntelligenceRequirement, payload.matched_requirement_id
                )
                if matched_requirement is None:
                    reasons.append("匹配的情报需求不存在")
                elif matched_requirement.status is not IntelligenceRequirementStatus.ACTIVE:
                    reasons.append(f"匹配的情报需求非激活态：{matched_requirement.status.value}")
        else:  # REJECT：维持否决
            if payload.reason_type is None:
                reasons.append("维持否决缺少理由类型")

        if reasons:
            raise ProposalRejectedError(reasons)

        assert item is not None
        if payload.decision is ReviewDecisionEnum.PASS:
            item.status = ItemStatus.CANDIDATE

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
