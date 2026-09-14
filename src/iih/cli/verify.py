"""核实子命令：扫所有 Candidate 态条目逐一核实评级并落账（IIH-01.03）。

每条 verify+execute 独立事务；单条失败不阻断其他。
本里程碑核实智能体不调 LLM，纯确定性评级。
"""

import argparse

from sqlalchemy import select

from iih.agents.verifier import Verifier
from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.ledger.models import IntelligenceItem, ItemStatus, VerificationOutcome
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor


def run(args: argparse.Namespace) -> int:
    """批量核实评级主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    # 独立会话扫 Candidate 态条目
    with session_factory() as session:
        candidate_items = list(
            session.scalars(
                select(IntelligenceItem).where(IntelligenceItem.status == ItemStatus.CANDIDATE)
            )
        )
        candidate_ids = [item.id for item in candidate_items]

    if not candidate_ids:
        print("无 Candidate 态条目待核实。")
        engine.dispose()
        return 0

    print(f"待核实 {len(candidate_ids)} 条 Candidate。")
    stats = {"verified": 0, "undetermined": 0, "failed": 0}

    for item_id in candidate_ids:
        with session_factory() as session:
            item = session.get(IntelligenceItem, item_id)
            if item is None or item.status is not ItemStatus.CANDIDATE:
                continue

            verifier = Verifier(session=session)
            try:
                proposal = verifier.verify(item)
            except Exception as exc:  # 公式异常等
                print(f"  [错误] 条目 #{item_id}：{exc}")
                stats["failed"] += 1
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                print(f"  [驳回] 条目 #{item_id}：{exc}")
                stats["failed"] += 1
                continue

            if proposal.payload.outcome is VerificationOutcome.VERIFIED:
                stats["verified"] += 1
                print(f"  [已核实] 条目 #{item_id} → Verified（评级 {proposal.payload.rating}）")
            else:
                stats["undetermined"] += 1
                print(f"  [存疑] 条目 #{item_id} → Undetermined（{proposal.rationale}）")

    print(
        f"\n汇总：待核实 {len(candidate_ids)}，已核实 {stats['verified']}，"
        f"存疑 {stats['undetermined']}，失败 {stats['failed']}"
    )
    engine.dispose()
    return 0
