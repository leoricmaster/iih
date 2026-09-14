"""采集子命令：跑通 Director→fetcher→Collector→executor 链路（IIH-01.08）。

每条 fetch+collect+execute 独立事务；单条失败不阻断其他。
LLM 失败、fetcher 失败、提案驳回分别记日志后继续。
"""

import argparse

from iih.agents.collector import Collector
from iih.agents.director import Director
from iih.agents.llm import make_llm_client
from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.tools.fetcher import FetcherError, fetch


def run(args: argparse.Namespace) -> int:
    """自动拉取主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    llm = make_llm_client(settings)

    # 先在独立会话扫任务（Director 不调 LLM、不写账）
    with session_factory() as session:
        tasks = Director(session).propose_tasks()
    if not tasks:
        print("无激活情报需求或无已登记互联网途径，未产出任务。")
        engine.dispose()
        return 0

    print(f"派单 {len(tasks)} 个采集任务。")
    stats = {"fetched": 0, "new": 0, "appended": 0, "skipped": 0, "failed": 0}

    for task in tasks:
        try:
            html = fetch(task.url)
        except FetcherError as exc:
            print(f"  [跳过] {task.source_name}·{task.outlet_name}：{exc}")
            stats["failed"] += 1
            continue
        stats["fetched"] += 1

        with session_factory() as session:
            collector = Collector(llm=llm, session=session, model=settings.llm_model)
            try:
                proposal = collector.collect_outlet(task=task, html=html)
            except Exception as exc:  # LLM 调用失败等
                print(f"  [错误] {task.source_name}·{task.outlet_name}：{exc}")
                stats["failed"] += 1
                continue

            if proposal is None:
                print(f"  [空] {task.source_name}·{task.outlet_name}：LLM 判定无情报价值")
                stats["skipped"] += 1
                continue

            try:
                StateMachineExecutor().execute(proposal, session=session)
            except ProposalRejectedError as exc:
                print(f"  [驳回] {task.source_name}·{task.outlet_name}：{exc}")
                stats["failed"] += 1
                continue

            from iih.ledger.proposal import IntelligenceItemNewProposal

            if isinstance(proposal, IntelligenceItemNewProposal):
                stats["new"] += 1
                print(f"  [新建] {task.source_name}·{task.outlet_name}：线索已落账")
            else:
                stats["appended"] += 1
                print(f"  [追加] {task.source_name}·{task.outlet_name}：转引链节点已追加")

    print(
        f"\n汇总：任务 {len(tasks)}，抓取 {stats['fetched']}，"
        f"新建条目 {stats['new']}，追加节点 {stats['appended']}，"
        f"跳过 {stats['skipped']}，失败 {stats['failed']}"
    )
    engine.dispose()
    return 0
