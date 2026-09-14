"""审查子命令：扫所有 Lead 态条目逐一审查并落账（IIH-01.02）。

每条 review+execute 独立事务；单条失败不阻断其他。
LLM 失败、提案驳回分别记日志后继续。
"""

import argparse

from sqlalchemy import select

from iih.agents.llm import make_llm_client
from iih.agents.reviewer import Reviewer
from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.ledger.models import IntelligenceItem, ItemStatus
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor


def run(args: argparse.Namespace) -> int:
    """批量审查主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    llm = make_llm_client(settings)

    # 独立会话扫 Lead 态条目
    with session_factory() as session:
        lead_items = list(
            session.scalars(
                select(IntelligenceItem).where(IntelligenceItem.status == ItemStatus.LEAD)
            )
        )
        # 预取 id 列表，避免跨会话持有 ORM 对象
        lead_ids = [item.id for item in lead_items]

    if not lead_ids:
        print("无 Lead 态条目待审查。")
        engine.dispose()
        return 0

    print(f"待审查 {len(lead_ids)} 条 Lead。")
    stats = {"passed": 0, "rejected": 0, "failed": 0}

    for item_id in lead_ids:
        with session_factory() as session:
            item = session.get(IntelligenceItem, item_id)
            if item is None or item.status is not ItemStatus.LEAD:
                # 状态已变（如人工或前一轮已审查），跳过
                continue

            reviewer = Reviewer(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = reviewer.review(item)
            except Exception as exc:  # LLM 调用失败等
                print(f"  [错误] 条目 #{item_id}：{exc}")
                stats["failed"] += 1
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                print(f"  [驳回] 条目 #{item_id}：{exc}")
                stats["failed"] += 1
                continue

            from iih.ledger.models import ReviewDecisionEnum

            if proposal.payload.decision is ReviewDecisionEnum.PASS:
                stats["passed"] += 1
                print(f"  [通过] 条目 #{item_id} → Candidate")
            else:
                stats["rejected"] += 1
                reason = (
                    proposal.payload.reason_type.value if proposal.payload.reason_type else "未知"
                )
                print(f"  [否决] 条目 #{item_id} → Noise（{reason}）")

    print(
        f"\n汇总：待审查 {len(lead_ids)}，通过 {stats['passed']}，"
        f"否决 {stats['rejected']}，失败 {stats['failed']}"
    )
    engine.dispose()
    return 0
