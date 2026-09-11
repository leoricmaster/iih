from datetime import UTC, datetime

from sqlalchemy import select

from iih.ledger.models import (
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    Medium,
    Modality,
    Source,
    SourceType,
)


def test_medium_seed_matches_glossary_closed_set(db_session) -> None:
    codes = set(db_session.scalars(select(Medium.code)))
    assert codes == {
        "internet",
        "user_interview",
        "industry_exhibition",
        "industry_exchange",
        "meeting_discussion",
        "document_reading",
    }


def test_modality_seed_covers_all_carriers(db_session) -> None:
    codes = set(db_session.scalars(select(Modality.code)))
    assert codes == {"webpage", "audio", "text", "image", "document"}


def test_intelligence_item_roundtrip(db_session) -> None:
    medium = db_session.scalars(select(Medium).where(Medium.code == "meeting_discussion")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "text")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=False)
    item = IntelligenceItem(
        statement="W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产",
        status=ItemStatus.LEAD,
        mode=ItemMode.MANUAL,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        original_snapshot="W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产",
        source=source,
    )
    db_session.add(item)
    db_session.flush()

    loaded = db_session.get(IntelligenceItem, item.id)
    assert loaded is not None
    assert loaded.status is ItemStatus.LEAD
    assert loaded.mode is ItemMode.MANUAL
    assert loaded.retracted is False
    assert loaded.source is not None and loaded.source.confirmed is False
    assert loaded.medium.name == "会议讨论"
    assert loaded.modality.name == "文字"
