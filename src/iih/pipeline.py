"""流水线一轮执行（doc-06 §2–§5 全链）：采集 → 审查 → 核实评级。

供 Web 层（「立即运行一轮」按钮、后台自动循环）与 CLI 复用；
每条 fetch/collect/review/verify 独立事务，单条失败不阻断其余。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from iih.agents.collector import Collector
from iih.agents.director import Director
from iih.agents.reviewer import Reviewer
from iih.agents.verifier import Verifier
from iih.config import Settings
from iih.ledger.models import (
    IntelligenceItem,
    ItemStatus,
    ReviewDecisionEnum,
    VerificationOutcome,
)
from iih.ledger.proposal import IntelligenceItemNewProposal
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.tools.fetcher import FetcherError, fetch

logger = logging.getLogger("iih.pipeline")

LogFn = Callable[[str], None]


@dataclass
class RoundSummary:
    """一轮流水线的结果计数与错误信息（供 UI 回显与日志）。"""

    tasks: int = 0
    fetched: int = 0
    new_items: int = 0
    appended_nodes: int = 0
    collect_skipped: int = 0
    collect_failed: int = 0
    review_passed: int = 0
    review_rejected: int = 0
    review_failed: int = 0
    verified: int = 0
    undetermined: int = 0
    verify_failed: int = 0
    errors: list[str] = field(default_factory=list)

    def flash(self) -> str:
        """UI 一行摘要。"""
        return (
            f"运行一轮完成：任务 {self.tasks}（新建 {self.new_items}、追加节点 "
            f"{self.appended_nodes}、跳过 {self.collect_skipped}、失败 {self.collect_failed}）；"
            f"审查 {self.review_passed + self.review_rejected}（通过 {self.review_passed}、"
            f"否决 {self.review_rejected}）；核实 {self.verified + self.undetermined}"
            f"（已核实 {self.verified}、存疑 {self.undetermined}）"
            + (f"；失败 {len(self.errors)} 项" if self.errors else "")
        )


def run_collect_stage(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    llm,
    summary: RoundSummary,
    log: LogFn | None = None,
) -> None:
    """采集段：Director 派单 → fetcher 抓取 → Collector 提案 → 执行器落账。"""

    def say(msg: str) -> None:
        if log is not None:
            log(msg)

    with session_factory() as session:
        tasks = Director(session).propose_tasks()
    summary.tasks = len(tasks)
    if not tasks:
        say("无激活情报需求或无已登记互联网途径，未产出采集任务。")
        return

    say(f"派单 {len(tasks)} 个采集任务。")
    for task in tasks:
        try:
            html = fetch(task.url)
        except FetcherError as exc:
            summary.collect_failed += 1
            summary.errors.append(f"抓取失败 {task.source_name}·{task.outlet_name}：{exc}")
            say(f"  [跳过] {task.source_name}·{task.outlet_name}：{exc}")
            continue
        summary.fetched += 1

        with session_factory() as session:
            collector = Collector(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = collector.collect_outlet(task=task, html=html)
            except Exception as exc:  # LLM 调用失败等
                summary.collect_failed += 1
                summary.errors.append(f"采集失败 {task.source_name}·{task.outlet_name}：{exc}")
                say(f"  [错误] {task.source_name}·{task.outlet_name}：{exc}")
                continue

            if proposal is None:
                summary.collect_skipped += 1
                say(f"  [空] {task.source_name}·{task.outlet_name}：LLM 判定无情报价值")
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                summary.collect_failed += 1
                summary.errors.append(f"提案驳回 {task.source_name}·{task.outlet_name}：{exc}")
                say(f"  [驳回] {task.source_name}·{task.outlet_name}：{exc}")
                continue

            if isinstance(proposal, IntelligenceItemNewProposal):
                summary.new_items += 1
                say(f"  [新建] {task.source_name}·{task.outlet_name}：线索已落账")
            else:
                summary.appended_nodes += 1
                say(f"  [追加] {task.source_name}·{task.outlet_name}：转引链节点已追加")


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
                select(IntelligenceItem.id).where(IntelligenceItem.status == ItemStatus.LEAD)
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
                select(IntelligenceItem.id).where(IntelligenceItem.status == ItemStatus.CANDIDATE)
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
    log: LogFn | None = None,
) -> RoundSummary:
    """完整一轮：采集 → 审查 → 核实。"""
    summary = RoundSummary()
    run_collect_stage(
        settings=settings, session_factory=session_factory, llm=llm, summary=summary, log=log
    )
    run_review_stage(
        settings=settings, session_factory=session_factory, llm=llm, summary=summary, log=log
    )
    run_verify_stage(session_factory=session_factory, summary=summary, log=log)
    logger.info("pipeline round: %s", summary.flash())
    return summary
