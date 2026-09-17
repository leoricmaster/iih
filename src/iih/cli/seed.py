"""种子数据子命令：版本化种子文件 → 落账，幂等（同名已存在则跳过/补激活）。

业界惯例：种子数据随仓库版本化、命令显式执行、可重复运行；
与单测 fixture 分离——单测面向内存库构造场景，种子面向开发/验收库铺基线。
信源种子直接 ORM 铺底（IIH-06.01 人工登记提案废弃；种子非智能体提案，
无判断成分，确定性构造即可）；需求种子仍走提案落账。
用法：python -m iih.cli seed [--file 路径]（默认 src/iih/seeds/dev.json）。
"""

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.config import get_settings
from iih.db import make_engine, make_session_factory
from iih.ledger.models import (
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Medium,
    Outlet,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceRequirementActivatePayload,
    IntelligenceRequirementActivateProposal,
    IntelligenceRequirementRegisterPayload,
    IntelligenceRequirementRegisterProposal,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor

DEFAULT_SEED_FILE = Path(__file__).resolve().parent.parent / "seeds" / "dev.json"

SEED_RATIONALE = "种子数据"


def _parse_date(s: str | None) -> date | None:
    if not s or not s.strip():
        return None
    return date.fromisoformat(s.strip())


def _seed_sources(session: Session, sources: list[dict[str, str]]) -> None:
    medium = session.scalars(select(Medium).where(Medium.code == "internet")).first()
    if medium is None:
        print("[seed] 媒介 internet 缺失，信源种子跳过")
        return
    for src in sources:
        existing = session.scalars(select(Source).where(Source.name == src["source_name"])).first()
        if existing is not None:
            print(f"[seed] 信源已存在，跳过：{src['source_name']}")
            continue
        source = Source(
            name=src["source_name"],
            type=SourceType(src["source_type"]),
            confirmed=True,
            credit=src.get("initial_credit") or None,
        )
        session.add(
            Outlet(
                source=source,
                name=src["outlet_name"],
                entry=src["outlet_entry"],
                medium=medium,
            )
        )
        session.flush()
        print(f"[seed] 铺底信源：{src['source_name']}（{src['outlet_name']}）")
    session.commit()


def _seed_requirements(session: Session, requirements: list[dict[str, str]]) -> None:
    for req in requirements:
        ir = session.scalars(
            select(IntelligenceRequirement).where(IntelligenceRequirement.name == req["name"])
        ).first()
        if ir is None:
            try:
                result = StateMachineExecutor().execute(
                    IntelligenceRequirementRegisterProposal(
                        payload=IntelligenceRequirementRegisterPayload(
                            name=req["name"],
                            content_spec=req["content_spec"],
                            collection_frequency=req.get("collection_frequency") or None,
                            event_freshness=req.get("event_freshness") or None,
                            valid_from=_parse_date(req.get("valid_from")),
                            valid_until=_parse_date(req.get("valid_until")),
                            source_ids=req.get("source_ids", []),
                        ),
                        rationale=SEED_RATIONALE,
                    ),
                    session=session,
                )
                ir = session.get(IntelligenceRequirement, result.requirement_id)
                print(f"[seed] 登记需求：{req['name']}")
            except ProposalRejectedError as exc:
                print(f"[seed] 需求登记失败：{req['name']}：{exc}")
                continue
        else:
            print(f"[seed] 需求已存在：{req['name']}")
        if (
            req.get("activate")
            and ir is not None
            and ir.status is IntelligenceRequirementStatus.DRAFT
        ):
            try:
                StateMachineExecutor().execute(
                    IntelligenceRequirementActivateProposal(
                        payload=IntelligenceRequirementActivatePayload(requirement_id=ir.id),
                        rationale=SEED_RATIONALE,
                    ),
                    session=session,
                )
                print(f"[seed] 激活需求：{req['name']}")
            except ProposalRejectedError as exc:
                print(f"[seed] 需求激活失败：{req['name']}：{exc}")


def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    with session_factory() as session:
        _seed_sources(session, data.get("sources", []))
        _seed_requirements(session, data.get("requirements", []))
    engine.dispose()
    return 0
