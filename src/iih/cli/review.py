"""审查子命令：扫所有 Lead 态条目逐一审查并落账（IIH-01.02）。

核心循环复用 pipeline.run_review_stage；单条失败不阻断其他。
"""

import argparse

from iih.agents.llm import make_llm_client
from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.pipeline import RoundSummary, run_review_stage


def run(args: argparse.Namespace) -> int:
    """批量审查主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    llm = make_llm_client(settings)

    summary = RoundSummary()
    run_review_stage(
        settings=settings,
        session_factory=session_factory,
        llm=llm,
        summary=summary,
        log=print,
    )
    print(summary.flash())
    engine.dispose()
    return 0
