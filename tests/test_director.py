"""Director 单测（doc-06 §2 + IIH-03.01 + IIH-06.01）：激活 IR × 已确认信源采集入口笛卡尔积，
按各 IR 独立参数分发：到期关闭 + due 过滤 + 信源绑定过滤；探索常驻（每 due IR 无条件一个）。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from iih.agents.director import CollectionTask, Director
from iih.ledger.models import (
    Entry,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Source,
    SourceType,
)


def _seed_ir(
    db_session,
    *,
    name: str,
    status: IntelligenceRequirementStatus = IntelligenceRequirementStatus.ACTIVE,
    collection_frequency: str | None = None,
    event_freshness: str | None = None,
    valid_until=None,
    last_collected_at=None,
    sources: list[Source] | None = None,
) -> IntelligenceRequirement:
    ir = IntelligenceRequirement(
        name=name,
        content_spec="主题",
        status=status,
        collection_frequency=collection_frequency,
        event_freshness=event_freshness,
        valid_until=valid_until,
        last_collected_at=last_collected_at,
    )
    if sources:
        ir.sources = sources
    db_session.add(ir)
    db_session.flush()
    return ir


def _seed_entry(
    db_session,
    *,
    source_name: str,
    entry: str,
    confirmed: bool = True,
) -> Entry:
    source = Source(name=source_name, type=SourceType.COMPANY, confirmed=confirmed)
    entry_obj = Entry(source=source, entry=entry)
    db_session.add_all([source, entry_obj])
    db_session.flush()
    return entry_obj


def test_propose_tasks_returns_cartesian_product(db_session) -> None:
    """激活 IR × 已确认信源采集入口：2 IR × 2 入口 = 4 采集任务 + 2 探索任务。"""
    _seed_ir(db_session, name="跟踪 W 公司")
    _seed_ir(db_session, name="跟踪新华社")
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example/news")
    _seed_entry(db_session, source_name="新华社", entry="https://xinhua.example")

    tasks, explorations = Director(db_session).propose_tasks()

    assert len(tasks) == 4
    assert all(isinstance(t, CollectionTask) for t in tasks)
    assert {t.requirement_name for t in tasks} == {"跟踪 W 公司", "跟踪新华社"}
    assert {t.source_name for t in tasks} == {"W 公司", "新华社"}
    assert len(explorations) == 2  # 每 due IR 一个
    assert {e.requirement_name for e in explorations} == {"跟踪 W 公司", "跟踪新华社"}


def test_propose_tasks_excludes_paused_and_draft_irs(db_session) -> None:
    _seed_ir(db_session, name="激活", status=IntelligenceRequirementStatus.ACTIVE)
    _seed_ir(db_session, name="草稿", status=IntelligenceRequirementStatus.DRAFT)
    _seed_ir(db_session, name="暂停", status=IntelligenceRequirementStatus.PAUSED)
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    tasks, explorations = Director(db_session).propose_tasks()

    assert len(tasks) == 1
    assert tasks[0].requirement_name == "激活"
    assert [e.requirement_name for e in explorations] == ["激活"]


def test_propose_tasks_cold_start_dispatches_exploration_only(db_session) -> None:
    """IIH-06.01：信源池为空 → 无采集任务，但探索任务照派（解冷启动）。"""
    ir = _seed_ir(db_session, name="激活")

    tasks, explorations = Director(db_session).propose_tasks()

    assert tasks == []
    assert len(explorations) == 1
    assert explorations[0].requirement_id == ir.id
    assert explorations[0].content_spec == "主题"  # 检索词来源


def test_propose_tasks_excludes_unconfirmed_sources(db_session) -> None:
    _seed_ir(db_session, name="激活")
    _seed_entry(
        db_session,
        source_name="待确认",
        entry="https://x.example",
        confirmed=False,
    )

    tasks, explorations = Director(db_session).propose_tasks()

    assert tasks == []
    assert len(explorations) == 1


def test_propose_tasks_empty_when_no_active_irs(db_session) -> None:
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    assert Director(db_session).propose_tasks() == ([], [])


# ---- IIH-03.01 需求级采集配置 ----


def test_frequency_due_when_never_collected(db_session) -> None:
    """从未采集的 IR 始终 due（不管频率）。"""
    _seed_ir(db_session, name="高频", collection_frequency="1h")
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    tasks, explorations = Director(db_session).propose_tasks()

    assert len(tasks) == 1
    assert tasks[0].requirement_name == "高频"
    assert len(explorations) == 1


def test_frequency_not_due_when_recently_collected(db_session) -> None:
    """配置 1h 频率，10 分钟前刚采集过 → 未 due，跳过本轮（采集与探索均不派）。"""
    just_now = datetime.now(UTC) - timedelta(minutes=10)
    _seed_ir(
        db_session,
        name="高频",
        collection_frequency="1h",
        last_collected_at=just_now,
    )
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    assert Director(db_session).propose_tasks() == ([], [])


def test_frequency_due_when_window_elapsed(db_session) -> None:
    """配置 1h 频率，2 小时前采集过 → 已 due，本轮派单。"""
    two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
    _seed_ir(
        db_session,
        name="高频",
        collection_frequency="1h",
        last_collected_at=two_hours_ago,
    )
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    tasks, explorations = Director(db_session).propose_tasks()

    assert len(tasks) == 1
    assert tasks[0].requirement_name == "高频"
    assert len(explorations) == 1


def test_frequency_inherit_global_when_empty(db_session, monkeypatch) -> None:
    """频率为空 → 用全局 pipeline_interval_seconds。"""
    from iih.agents import director as director_module
    from iih.config import get_settings

    settings = get_settings().model_copy(update={"pipeline_interval_seconds": 300})
    monkeypatch.setattr(director_module, "get_settings", lambda: settings)

    just_now = datetime.now(UTC) - timedelta(seconds=60)
    _seed_ir(db_session, name="继承全局", last_collected_at=just_now)
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    # 60s < 300s 未 due
    assert Director(db_session).propose_tasks() == ([], [])

    # 6 分钟前刚采集过（360s > 300s），已 due
    six_minutes_ago = datetime.now(UTC) - timedelta(seconds=360)
    ir = db_session.scalars(select(IntelligenceRequirement)).first()
    assert ir is not None
    ir.last_collected_at = six_minutes_ago
    db_session.flush()
    tasks, explorations = Director(db_session).propose_tasks()
    assert len(tasks) == 1
    assert len(explorations) == 1


def test_source_binding_filters_entries(db_session) -> None:
    """IR 绑定 [S1] → 仅派单到 S1 入口；未绑定 IR 派单到全部。探索不受绑定过滤。"""
    s1 = Source(name="S1", type=SourceType.COMPANY, confirmed=True)
    s2 = Source(name="S2", type=SourceType.COMPANY, confirmed=True)
    e1 = Entry(source=s1, entry="https://s1.example")
    e2 = Entry(source=s2, entry="https://s2.example")
    db_session.add_all([s1, s2, e1, e2])
    db_session.flush()
    _seed_ir(db_session, name="绑定 S1", sources=[s1])
    _seed_ir(db_session, name="不绑定")

    tasks, explorations = Director(db_session).propose_tasks()

    # 绑定 S1 的 IR：1 任务（S1 入口）；不绑定的 IR：2 任务（全部入口）= 3 总
    assert len(tasks) == 3
    bound_tasks = [t for t in tasks if t.requirement_name == "绑定 S1"]
    unbound_tasks = [t for t in tasks if t.requirement_name == "不绑定"]
    assert len(bound_tasks) == 1
    assert bound_tasks[0].source_name == "S1"
    assert {t.source_name for t in unbound_tasks} == {"S1", "S2"}
    assert len(explorations) == 2


def test_auto_close_expired_ir(db_session) -> None:
    """valid_until ≤ today 的激活 IR 自动落 Close 提案，从派单列表移除。"""
    today = datetime.now(UTC).date()
    _seed_ir(
        db_session,
        name="已到期",
        valid_until=today - timedelta(days=1),
    )
    _seed_ir(db_session, name="未到期")
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    tasks, explorations = Director(db_session).propose_tasks()

    # 已到期 IR 被关闭，不再派单；只有未到期 IR 的 1 任务 + 1 探索
    assert len(tasks) == 1
    assert tasks[0].requirement_name == "未到期"
    assert [e.requirement_name for e in explorations] == ["未到期"]

    expired = db_session.scalars(
        select(IntelligenceRequirement).where(IntelligenceRequirement.name == "已到期")
    ).one()
    assert expired.status is IntelligenceRequirementStatus.CLOSED


def test_valid_until_today_triggers_close(db_session) -> None:
    """valid_until = today（≤ today）也触发关闭。"""
    today = datetime.now(UTC).date()
    _seed_ir(db_session, name="今日到期", valid_until=today)
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    Director(db_session).propose_tasks()

    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert ir.status is IntelligenceRequirementStatus.CLOSED


def test_valid_until_future_not_closed(db_session) -> None:
    """valid_until 在未来 → 不关闭，正常派单。"""
    future = datetime.now(UTC).date() + timedelta(days=30)
    _seed_ir(db_session, name="未来到期", valid_until=future)
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    tasks, explorations = Director(db_session).propose_tasks()

    assert len(tasks) == 1
    assert len(explorations) == 1
    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert ir.status is IntelligenceRequirementStatus.ACTIVE


def test_auto_close_handles_paused_ir_without_closing(db_session) -> None:
    """暂停态 IR 即使 valid_until 到期也不自动关闭（仅激活态触发）。"""
    today = datetime.now(UTC).date()
    _seed_ir(
        db_session,
        name="暂停且到期",
        status=IntelligenceRequirementStatus.PAUSED,
        valid_until=today - timedelta(days=1),
    )
    _seed_entry(db_session, source_name="W 公司", entry="https://w.example")

    Director(db_session).propose_tasks()

    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert ir.status is IntelligenceRequirementStatus.PAUSED
