"""采集子命令：跑通 Director→fetcher→Collector→executor 链路（IIH-01.08）。

核心循环复用 pipeline.run_collect_stage；单条失败不阻断其他。
"""

import argparse

from iih.agents.llm import make_llm_client
from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.pipeline import RoundSummary, run_collect_stage


def run(args: argparse.Namespace) -> int:
    """自动拉取主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    llm = make_llm_client(settings)

    summary = RoundSummary()
    run_collect_stage(
        settings=settings,
        session_factory=session_factory,
        llm=llm,
        summary=summary,
        log=print,
    )
    print(summary.flash())
    engine.dispose()
    return 0
