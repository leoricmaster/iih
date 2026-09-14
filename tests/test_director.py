"""Director 单测（doc-06 §2 最简版）：激活 IR × 已确认互联网途径笛卡尔积。"""

from sqlalchemy import select

from iih.agents.director import CollectionTask, Director
from iih.ledger.models import (
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Medium,
    Outlet,
    Source,
    SourceType,
)


def _seed_ir(
    db_session, *, name: str, status: IntelligenceRequirementStatus
) -> IntelligenceRequirement:
    ir = IntelligenceRequirement(name=name, content_spec="主题", status=status)
    db_session.add(ir)
    db_session.flush()
    return ir


def _seed_outlet(
    db_session,
    *,
    source_name: str,
    outlet_name: str,
    entry: str,
    confirmed: bool = True,
    medium_code: str = "internet",
) -> Outlet:
    medium = db_session.scalars(select(Medium).where(Medium.code == medium_code)).one()
    source = Source(name=source_name, type=SourceType.COMPANY, confirmed=confirmed)
    outlet = Outlet(source=source, name=outlet_name, entry=entry, medium=medium)
    db_session.add_all([source, outlet])
    db_session.flush()
    return outlet


def test_propose_tasks_returns_cartesian_product(db_session) -> None:
    """激活 IR × 已确认互联网途径：2 IR × 2 途径 = 4 任务。"""
    _seed_ir(db_session, name="跟踪 W 公司", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_ir(db_session, name="跟踪新华社", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_outlet(
        db_session, source_name="W 公司", outlet_name="官网", entry="https://w.example/news"
    )
    _seed_outlet(
        db_session, source_name="新华社", outlet_name="官网", entry="https://xinhua.example"
    )

    tasks = Director(db_session).propose_tasks()

    assert len(tasks) == 4
    assert all(isinstance(t, CollectionTask) for t in tasks)
    assert {t.requirement_name for t in tasks} == {"跟踪 W 公司", "跟踪新华社"}
    assert {t.source_name for t in tasks} == {"W 公司", "新华社"}
    assert all(t.url.startswith("https://") for t in tasks)


def test_propose_tasks_excludes_paused_and_draft_irs(db_session) -> None:
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_ir(db_session, name="草稿", status=IntelligenceRequirementStatus.DRAFT)
    _seed_ir(db_session, name="暂停", status=IntelligenceRequirementStatus.PAUSED)
    _seed_outlet(db_session, source_name="W 公司", outlet_name="官网", entry="https://w.example")

    tasks = Director(db_session).propose_tasks()

    assert len(tasks) == 1
    assert tasks[0].requirement_name == "激活"


def test_propose_tasks_excludes_unconfirmed_sources(db_session) -> None:
    """未确认信源不入正式池、不参与采集（decision-05）。"""
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_outlet(
        db_session,
        source_name="待确认",
        outlet_name="官网",
        entry="https://x.example",
        confirmed=False,
    )

    tasks = Director(db_session).propose_tasks()

    assert tasks == []


def test_propose_tasks_excludes_non_internet_outlets(db_session) -> None:
    """仅互联网途径派单；线下场景经素材录入归因。"""
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_outlet(
        db_session,
        source_name="W 公司",
        outlet_name="现场",
        entry="行业大会",
        confirmed=True,
        medium_code="meeting_discussion",
    )

    tasks = Director(db_session).propose_tasks()

    assert tasks == []


def test_propose_tasks_skips_outlets_without_entry(db_session) -> None:
    """途径 entry 为空无法派单。"""
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    outlet = Outlet(source=source, name="官网", entry=None, medium=medium)
    db_session.add_all([source, outlet])
    db_session.flush()

    tasks = Director(db_session).propose_tasks()

    assert tasks == []


def test_propose_tasks_empty_when_no_active_irs(db_session) -> None:
    _seed_outlet(db_session, source_name="W 公司", outlet_name="官网", entry="https://w.example")

    assert Director(db_session).propose_tasks() == []


def test_propose_tasks_empty_when_no_confirmed_internet_outlets(db_session) -> None:
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)

    assert Director(db_session).propose_tasks() == []
