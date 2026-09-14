"""情报需求子命令：ir-create / ir-activate（doc-02 §4.1 状态机）。"""

import argparse

from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.ledger.proposal import (
    IntelligenceRequirementActivatePayload,
    IntelligenceRequirementActivateProposal,
    IntelligenceRequirementRegisterPayload,
    IntelligenceRequirementRegisterProposal,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor


def ir_create(args: argparse.Namespace) -> int:
    """情报需求登记：[*] → Draft。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        proposal = IntelligenceRequirementRegisterProposal(
            payload=IntelligenceRequirementRegisterPayload(name=args.name, content_spec=args.spec),
            rationale="CLI 登记（消费方声明）",
        )
        try:
            result = StateMachineExecutor().execute(proposal, session=session)
        except ProposalRejectedError as exc:
            print(f"登记失败：{exc}")
            return 1
        print(
            f"已登记情报需求 #{result.requirement_id}（Draft）。"
            f"激活：python -m iih.cli ir-activate {result.requirement_id}"
        )
    engine.dispose()
    return 0


def ir_activate(args: argparse.Namespace) -> int:
    """情报需求激活：Draft → Active。"""
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        proposal = IntelligenceRequirementActivateProposal(
            payload=IntelligenceRequirementActivatePayload(requirement_id=args.requirement_id),
            rationale="CLI 激活",
        )
        try:
            StateMachineExecutor().execute(proposal, session=session)
        except ProposalRejectedError as exc:
            print(f"激活失败：{exc}")
            return 1
        print(f"已激活情报需求 #{args.requirement_id}（Active）。")
    engine.dispose()
    return 0
