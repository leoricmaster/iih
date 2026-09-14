"""核实子命令：扫所有 Candidate 态条目逐一核实评级并落账（IIH-01.03）。

核心循环复用 pipeline.run_verify_stage；本里程碑核实智能体不调 LLM。
"""

import argparse

from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.pipeline import RoundSummary, run_verify_stage


def run(args: argparse.Namespace) -> int:
    """批量核实评级主链路。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    summary = RoundSummary()
    run_verify_stage(session_factory=session_factory, summary=summary, log=print)
    print(summary.flash())
    engine.dispose()
    return 0
