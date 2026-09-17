"""流水线一轮执行（doc-06 §2–§5 全链）：素材加工 → 采集 → 审查 → 核实评级。

供 Web 层（「立即运行一轮」按钮、后台自动循环）与 CLI 复用；
每条 fetch/collect/review/verify 独立事务，单条失败不阻断其余。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, sessionmaker

from iih.agents.collector import Collector
from iih.agents.director import Director
from iih.agents.reviewer import Reviewer
from iih.agents.verifier import Verifier
from iih.config import Settings
from iih.ledger.models import (
    Derivation,
    DerivationProducer,
    IntelligenceItem,
    ItemStatus,
    Material,
    MaterialStatus,
    ReviewDecisionEnum,
    VerificationOutcome,
)
from iih.ledger.proposal import IntelligenceItemNewProposal
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.tools.asr import TingwuAsr, TingwuAsrError
from iih.tools.fetcher import FetcherError, fetch
from iih.tools.snapshot_store import SnapshotStore

logger = logging.getLogger("iih.pipeline")

LogFn = Callable[[str], None]

MAX_MATERIAL_RETRIES = 3  # 自动重试上限，达上限转人工（重试按钮）

DONE = "done"  # 本步推进到完成（素材级终态）
PENDING = "pending"  # 本步未完成（在途 / 未抢占到）
FAILED = "failed"  # 本步失败留痕（AC#2）


@dataclass
class RoundSummary:
    """一轮流水线的结果计数与错误信息（供 UI 回显与日志）。"""

    tasks: int = 0
    fetched: int = 0
    new_items: int = 0
    appended_nodes: int = 0
    collect_skipped: int = 0
    collect_failed: int = 0
    explored: int = 0
    explore_new_items: int = 0
    explore_failed: int = 0
    review_passed: int = 0
    review_rejected: int = 0
    review_failed: int = 0
    verified: int = 0
    undetermined: int = 0
    verify_failed: int = 0
    material_done: int = 0
    material_failed: int = 0
    errors: list[str] = field(default_factory=list)

    def flash(self) -> str:
        """UI 一行摘要。"""
        material_part = (
            f"；素材 {self.material_done + self.material_failed}"
            f"（完成 {self.material_done}、失败 {self.material_failed}）"
            if self.material_done or self.material_failed
            else ""
        )
        exploration_part = (
            f"；探索 {self.explored}（新建 {self.explore_new_items}、失败 {self.explore_failed}）"
            if self.explored or self.explore_failed
            else ""
        )
        return (
            f"运行一轮完成：任务 {self.tasks}（新建 {self.new_items}、追加节点 "
            f"{self.appended_nodes}、跳过 {self.collect_skipped}、失败 {self.collect_failed}）；"
            f"审查 {self.review_passed + self.review_rejected}（通过 {self.review_passed}、"
            f"否决 {self.review_rejected}）；核实 {self.verified + self.undetermined}"
            f"（已核实 {self.verified}、存疑 {self.undetermined}）"
            + material_part
            + exploration_part
            + (f"；失败 {len(self.errors)} 项" if self.errors else "")
        )


def _claim(
    session: Session, material_id: int, from_statuses: tuple[MaterialStatus, ...], **values
) -> bool:
    """条件抢占（乐观迁移）：from_statuses 内才写入，并发方后到即失效。"""
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(Material)
            .where(Material.id == material_id, Material.status.in_(from_statuses))
            .values(**values)
        ),
    )
    session.commit()
    return result.rowcount == 1


def _material_fail(
    session: Session, material: Material, *, to_status: MaterialStatus, reason: str
) -> None:
    """失败留痕（AC#2）：状态 + 原因 + 重试计数，可被循环自动重试或人工重试。"""
    claimed = _claim(
        session,
        material.id,
        (material.status,),
        status=to_status,
        failure_reason=reason[:2000],
        retry_count=material.retry_count + 1,
    )
    if not claimed:
        session.rollback()


def process_material(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    asr: TingwuAsr,
    store: SnapshotStore | None,
    material_id: int,
    log: LogFn | None = None,
) -> str:
    """单个素材推进一步（doc-02 §4.5）：提交 / 轮询 / 抽取，返回 done | pending | failed。

    每素材独立事务；上传端点（事件驱动）与循环兜底共用本入口，条件抢占防双跑；
    转写完成停「待标记」，经 Web 发言人标记（全部实名）转抽取中后本入口才抽取；
    失败留痕不抛出（AC#2 不静默、不产半成品——线索仅在转写稿派生存在后落账）。
    """
    say = log or (lambda _msg: None)
    with session_factory() as session:
        material = session.get(Material, material_id)
        if material is None:
            return PENDING

        # 加工：提交转写任务，或轮询已提交任务
        if material.status in (
            MaterialStatus.UPLOADED,
            MaterialStatus.PROCESSING,
            MaterialStatus.PROCESS_FAILED,
        ):
            if material.status is MaterialStatus.PROCESSING and material.external_task_id:
                try:
                    result = asr.check(material.external_task_id)
                except TingwuAsrError as exc:
                    _material_fail(
                        session, material, to_status=MaterialStatus.PROCESS_FAILED, reason=str(exc)
                    )
                    say(f"  [失败] 素材 #{material.id} 转写：{exc}")
                    return FAILED
                if result is None:
                    return PENDING  # 未完成，下轮再查
                # 派生落账与状态迁移同事务：抢占失败即他方已办
                # 停「待标记」：转写完成先经人工发言人标记（全部实名）再抽取
                transitioned = (
                    cast(
                        "CursorResult[Any]",
                        session.execute(
                            update(Material)
                            .where(
                                Material.id == material.id,
                                Material.status == MaterialStatus.PROCESSING,
                            )
                            .values(
                                status=MaterialStatus.TRANSCRIBED,
                                duration_seconds=result.duration_seconds,
                                failure_reason=None,
                            )
                        ),
                    ).rowcount
                    == 1
                )
                if transitioned:
                    session.add(
                        Derivation(
                            material_id=material.id,
                            producer=DerivationProducer.TOOL,
                            producer_ref="tingwu-offline",
                            output_text=result.text,
                            duration_seconds=result.duration_seconds,
                        )
                    )
                session.commit()
                if not transitioned:
                    return PENDING
                say(
                    f"  [转写完成] 素材 #{material.id}：{result.duration_seconds}s "
                    "转写稿已派生，待标记发言人"
                )
                session.refresh(material)
            else:
                # uploaded / process_failed（含自动重试）/ processing 丢任务号（崩溃恢复）→ 提交
                if (
                    material.status is MaterialStatus.PROCESS_FAILED
                    and material.retry_count >= MAX_MATERIAL_RETRIES
                ):
                    return PENDING  # 达上限，转人工
                if not _claim(
                    session,
                    material.id,
                    (
                        MaterialStatus.UPLOADED,
                        MaterialStatus.PROCESS_FAILED,
                        MaterialStatus.PROCESSING,
                    ),
                    status=MaterialStatus.PROCESSING,
                    external_task_id=None,
                ):
                    return PENDING
                if store is None:
                    return PENDING
                session.expire(material)
                try:
                    audio = store.get_material(material.object_key)
                    task_id = asr.submit(audio, material.filename)
                except Exception as exc:  # ASR/对象存储不可用：留痕待重试
                    _material_fail(
                        session, material, to_status=MaterialStatus.PROCESS_FAILED, reason=str(exc)
                    )
                    say(f"  [失败] 素材 #{material.id} 提交转写：{exc}")
                    return FAILED
                _claim(
                    session,
                    material.id,
                    (MaterialStatus.PROCESSING,),
                    external_task_id=task_id,
                )
                say(f"  [转写中] 素材 #{material.id} {material.filename}")
                return PENDING

        # 抽取：转写稿派生 → 陈述落账（零陈述亦完成留痕）
        if material.status in (MaterialStatus.EXTRACTING, MaterialStatus.EXTRACT_FAILED):
            if (
                material.status is MaterialStatus.EXTRACT_FAILED
                and material.retry_count >= MAX_MATERIAL_RETRIES
            ):
                return PENDING  # 达上限，转人工
            derivation = session.scalars(
                select(Derivation)
                .where(Derivation.material_id == material.id, Derivation.output_text.isnot(None))
                .order_by(Derivation.id.desc())
            ).first()
            if derivation is None:
                _material_fail(
                    session,
                    material,
                    to_status=MaterialStatus.EXTRACT_FAILED,
                    reason="无可抽取的转写稿派生",
                )
                return FAILED
            collector = Collector(llm=llm, session=session, model=settings.llm_model)
            try:
                proposals = collector.submit_material(material=material, derivation=derivation)
            except Exception as exc:  # LLM 调用失败等
                _material_fail(
                    session,
                    material,
                    to_status=MaterialStatus.EXTRACT_FAILED,
                    reason=f"抽取失败：{exc}",
                )
                say(f"  [失败] 素材 #{material.id} 抽取：{exc}")
                return FAILED
            created = 0
            for proposal in proposals:
                try:
                    StateMachineExecutor().execute(proposal, session=session)
                    created += 1
                except ProposalRejectedError:
                    pass  # 重复陈述等逐条驳回，不算素材失败
            claimed = _claim(
                session,
                material.id,
                (MaterialStatus.EXTRACTING, MaterialStatus.EXTRACT_FAILED),
                status=MaterialStatus.COMPLETED,
                retry_count=0,
                failure_reason=None,
            )
            if not claimed:
                return PENDING
            say(f"  [完成] 素材 #{material.id}：落账 {created} 条线索")
            return DONE

        return PENDING


def run_material_stage(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    asr: TingwuAsr | None,
    store: SnapshotStore | None = None,
    summary: RoundSummary | None = None,
    log: LogFn | None = None,
) -> None:
    """素材段（doc-02 §4.5）：兜底推进全部在途素材。

    上传端点已内联即时提交（事件驱动）；本段接手未提交的 uploaded、轮询 processing、
    抽取 extracting、自动重试未达上限的失败素材。待标记素材留待人工（不经本段）。
    ASR 未配置则跳过（素材留队不失败）。
    """
    say = log or (lambda _msg: None)
    if asr is None:
        say("听悟 ASR 未配置，素材段跳过。")
        return

    with session_factory() as session:
        statuses = (
            MaterialStatus.UPLOADED,
            MaterialStatus.PROCESSING,
            MaterialStatus.EXTRACTING,
            MaterialStatus.PROCESS_FAILED,
            MaterialStatus.EXTRACT_FAILED,
        )
        ids = list(session.scalars(select(Material.id).where(Material.status.in_(statuses))).all())
    if not ids:
        return

    say(f"在途素材 {len(ids)} 份。")
    for material_id in ids:
        try:
            outcome = process_material(
                settings=settings,
                session_factory=session_factory,
                llm=llm,
                asr=asr,
                store=store,
                material_id=material_id,
                log=log,
            )
            if summary is not None:
                if outcome == DONE:
                    summary.material_done += 1
                elif outcome == FAILED:
                    summary.material_failed += 1
        except Exception as exc:  # 防单素材异常阻断整段
            if summary is not None:
                summary.material_failed += 1
                summary.errors.append(f"素材 #{material_id} 处理异常：{exc}")
            say(f"  [错误] 素材 #{material_id}：{exc}")


def run_collect_stage(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    summary: RoundSummary,
    store: SnapshotStore | None = None,
    log: LogFn | None = None,
) -> None:
    """采集段：Director 派单（采集任务 + 探索任务）→ 抓取 → Collector 提案 → 执行器落账。

    每个 IR 完成本轮全部入口采集与探索后，更新 last_collected_at（IIH-03.01 调度差异化用）。
    """

    def say(msg: str) -> None:
        if log is not None:
            log(msg)

    with session_factory() as session:
        tasks, explorations = Director(session).propose_tasks()
    summary.tasks = len(tasks)
    if not tasks and not explorations:
        say("无到期情报需求，未产出采集任务。")
        return

    say(f"派单 {len(tasks)} 个采集任务、{len(explorations)} 个探索任务。")
    collected_requirement_ids: set[int] = set()
    for task in tasks:
        try:
            html = fetch(task.url)
        except FetcherError as exc:
            summary.collect_failed += 1
            summary.errors.append(f"抓取失败 {task.source_name}·{task.url}：{exc}")
            say(f"  [跳过] {task.source_name}·{task.url}：{exc}")
            continue
        summary.fetched += 1

        with session_factory() as session:
            collector = Collector(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = collector.collect_entry(
                    task=task,
                    html=html,
                    fetch_article=fetch,
                    store=store,
                )
            except Exception as exc:  # LLM 调用失败 / 文章页抓取失败等
                summary.collect_failed += 1
                summary.errors.append(f"采集失败 {task.source_name}·{task.url}：{exc}")
                say(f"  [错误] {task.source_name}·{task.url}：{exc}")
                continue

            if proposal is None:
                summary.collect_skipped += 1
                label = f"{task.source_name}·{task.url}"
                say(f"  [跳过] {label}：无新内容（已采集或无情报价值）")
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                summary.collect_failed += 1
                summary.errors.append(f"提案驳回 {task.source_name}·{task.url}：{exc}")
                say(f"  [驳回] {task.source_name}·{task.url}：{exc}")
                continue

            if isinstance(proposal, IntelligenceItemNewProposal):
                summary.new_items += 1
                say(f"  [新建] {task.source_name}·{task.url}：线索已落账")
            else:
                summary.appended_nodes += 1
                say(f"  [追加] {task.source_name}·{task.url}：转引链节点已追加")

            collected_requirement_ids.add(task.requirement_id)

    for exploration in explorations:
        with session_factory() as session:
            collector = Collector(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = collector.explore(task=exploration, fetch_article=fetch, store=store)
            except Exception as exc:  # LLM 调用失败等
                summary.explore_failed += 1
                summary.errors.append(f"探索失败 {exploration.requirement_name}：{exc}")
                say(f"  [错误] 探索 {exploration.requirement_name}：{exc}")
                continue
            summary.explored += 1

            if proposal is None:
                say(f"  [跳过] 探索 {exploration.requirement_name}：无新内容")
            else:
                try:
                    StateMachineExecutor().execute(proposal, session=session)
                except ProposalRejectedError as exc:
                    summary.explore_failed += 1
                    summary.errors.append(f"探索提案驳回 {exploration.requirement_name}：{exc}")
                    say(f"  [驳回] 探索 {exploration.requirement_name}：{exc}")
                    continue
                summary.explore_new_items += 1
                say(
                    f"  [新建] 探索 {exploration.requirement_name}："
                    f"{proposal.provenance.source_name} 线索已落账"
                )

            collected_requirement_ids.add(exploration.requirement_id)

    # IIH-03.01：本轮被派单过的 IR 更新 last_collected_at（一个 IR 一次）
    if collected_requirement_ids:
        from datetime import UTC, datetime

        from iih.ledger.models import IntelligenceRequirement

        with session_factory() as session:
            now = datetime.now(UTC)
            for ir_id in collected_requirement_ids:
                ir = session.get(IntelligenceRequirement, ir_id)
                if ir is not None:
                    ir.last_collected_at = now
            session.commit()


def run_review_stage(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    summary: RoundSummary,
    log: LogFn | None = None,
) -> None:
    """审查段：批量审查 Lead 态条目（doc-06 §4）。"""

    def say(msg: str) -> None:
        if log is not None:
            log(msg)

    with session_factory() as session:
        lead_ids = list(
            session.scalars(
                select(IntelligenceItem.id).where(
                    IntelligenceItem.status == ItemStatus.LEAD,
                    IntelligenceItem.retracted.is_(False),
                )
            )
        )
    if not lead_ids:
        say("无 Lead 态条目待审查。")
        return

    say(f"待审查 {len(lead_ids)} 条 Lead。")
    for item_id in lead_ids:
        with session_factory() as session:
            item = session.get(IntelligenceItem, item_id)
            if item is None or item.status is not ItemStatus.LEAD:
                continue  # 状态已变（人工或前一轮已处理）

            reviewer = Reviewer(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = reviewer.review(item)
            except Exception as exc:  # LLM 调用失败等
                summary.review_failed += 1
                summary.errors.append(f"审查失败 条目 #{item_id}：{exc}")
                say(f"  [错误] 条目 #{item_id}：{exc}")
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                summary.review_failed += 1
                summary.errors.append(f"审查提案驳回 条目 #{item_id}：{exc}")
                say(f"  [驳回] 条目 #{item_id}：{exc}")
                continue

            if proposal.payload.decision is ReviewDecisionEnum.PASS:
                summary.review_passed += 1
                say(f"  [通过] 条目 #{item_id} → Candidate")
            else:
                summary.review_rejected += 1
                reason = (
                    proposal.payload.reason_type.value if proposal.payload.reason_type else "未知"
                )
                say(f"  [否决] 条目 #{item_id} → Noise（{reason}）")


def run_verify_stage(
    *,
    session_factory: sessionmaker[Session],
    summary: RoundSummary,
    log: LogFn | None = None,
) -> None:
    """核实段：批量核实 Candidate 态条目（doc-06 §5；本里程碑不调 LLM）。"""

    def say(msg: str) -> None:
        if log is not None:
            log(msg)

    with session_factory() as session:
        candidate_ids = list(
            session.scalars(
                select(IntelligenceItem.id).where(
                    IntelligenceItem.status == ItemStatus.CANDIDATE,
                    IntelligenceItem.retracted.is_(False),
                )
            )
        )
    if not candidate_ids:
        say("无 Candidate 态条目待核实。")
        return

    say(f"待核实 {len(candidate_ids)} 条 Candidate。")
    for item_id in candidate_ids:
        with session_factory() as session:
            item = session.get(IntelligenceItem, item_id)
            if item is None or item.status is not ItemStatus.CANDIDATE:
                continue

            verifier = Verifier(session=session)
            try:
                proposal = verifier.verify(item)
            except Exception as exc:  # 公式异常等
                summary.verify_failed += 1
                summary.errors.append(f"核实失败 条目 #{item_id}：{exc}")
                say(f"  [错误] 条目 #{item_id}：{exc}")
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                summary.verify_failed += 1
                summary.errors.append(f"核实提案驳回 条目 #{item_id}：{exc}")
                say(f"  [驳回] 条目 #{item_id}：{exc}")
                continue

            if proposal.payload.outcome is VerificationOutcome.VERIFIED:
                summary.verified += 1
                say(f"  [已核实] 条目 #{item_id} → Verified（评级 {proposal.payload.rating}）")
            else:
                summary.undetermined += 1
                say(f"  [存疑] 条目 #{item_id} → Undetermined")


def run_pipeline_round(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    store: SnapshotStore | None = None,
    asr: TingwuAsr | None = None,
    log: LogFn | None = None,
) -> RoundSummary:
    """完整一轮：素材加工 → 采集 → 审查 → 核实。"""
    summary = RoundSummary()
    run_material_stage(
        settings=settings,
        session_factory=session_factory,
        llm=llm,
        asr=asr,
        store=store,
        summary=summary,
        log=log,
    )
    run_collect_stage(
        settings=settings,
        session_factory=session_factory,
        llm=llm,
        summary=summary,
        store=store,
        log=log,
    )
    run_review_stage(
        settings=settings, session_factory=session_factory, llm=llm, summary=summary, log=log
    )
    run_verify_stage(session_factory=session_factory, summary=summary, log=log)
    logger.info("pipeline round: %s", summary.flash())
    return summary
