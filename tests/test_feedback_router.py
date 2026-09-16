"""反馈路由（IIH-01.05）：校验落账 + 七类型分流（doc-02 §6、doc-07 §5 快捷反馈口径）。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from iih.ledger.feedback_router import (
    FEEDBACK_ROUTING,
    FeedbackChannel,
    FeedbackRejectedError,
    FeedbackRouter,
)
from iih.ledger.models import Feedback, FeedbackType, IntelligenceItem, ItemMode, ItemStatus

CREDIT = FeedbackChannel.CREDIT
DISPOSITION = FeedbackChannel.DISPOSITION
CONFIGURATION = FeedbackChannel.CONFIGURATION
ITERATION = FeedbackChannel.ITERATION


@pytest.fixture
def verified_item(db_session) -> IntelligenceItem:
    """预置一条已核实条目（反馈目标），溯源最简。"""
    from iih.ledger.models import Medium, Modality

    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.VERIFIED,
        rating="B2",
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="W 公司今日公告，与 Z 集团签署合资协议。",
    )
    db_session.add(item)
    db_session.flush()
    return item


def _submit(db_session, item_id: int, feedback_type: FeedbackType, reason: str = ""):
    return FeedbackRouter().submit(
        item_id=item_id, feedback_type=feedback_type, reason=reason, session=db_session
    )


def test_valid_quick_feedback_defaults_reason_and_routes_to_credit(
    db_session, verified_item
) -> None:
    """对应 IIH-01.05 AC#1：一键「有效」→ 默认理由「快捷 · 有效」落账，路由分流到信用通路。"""
    result = _submit(db_session, verified_item.id, FeedbackType.VALID)

    feedback = db_session.get(Feedback, result.feedback_id)
    assert feedback is not None
    assert feedback.item_id == verified_item.id
    assert feedback.reason == "快捷 · 有效"
    assert CREDIT in result.channels
    assert result.channels == frozenset({CREDIT, CONFIGURATION})  # 信用 ↑ + 配置正向微调


def test_blank_reason_filled_kept_as_written(db_session, verified_item) -> None:
    """Web 补写理由优先于默认理由（doc-07 §5）。"""
    _submit(db_session, verified_item.id, FeedbackType.OUTDATED, reason=" 事件已过一周 ")

    feedback = db_session.scalars(select(Feedback)).unique().one()
    assert feedback.reason == "事件已过一周"


def test_factual_error_without_reason_rejected(db_session, verified_item) -> None:
    """事实错误理由必填（doc-07 §5）：无理由驳回、不落账。"""
    with pytest.raises(FeedbackRejectedError) as excinfo:
        _submit(db_session, verified_item.id, FeedbackType.FACTUAL_ERROR)

    assert excinfo.value.reasons == ["事实错误反馈必须填写理由"]
    assert db_session.scalars(select(Feedback)).unique().first() is None


def test_factual_error_with_reason_lands_and_routes(db_session, verified_item) -> None:
    """事实错误带理由：落账 + 处置 / 信用 / 迭代三通路（doc-02 §6）。"""
    result = _submit(
        db_session, verified_item.id, FeedbackType.FACTUAL_ERROR, reason="协议从未签署"
    )

    feedback = db_session.get(Feedback, result.feedback_id)
    assert feedback.reason == "协议从未签署"
    assert result.channels == frozenset({DISPOSITION, CREDIT, ITERATION})


def test_factual_error_rejects_non_verified_item(noise_item, db_session) -> None:
    """事实错误仅对已核实条目开放（doc-02 §4：作废打在已核实条目上）——噪音态不给打作废标记。"""
    with pytest.raises(FeedbackRejectedError) as excinfo:
        _submit(db_session, noise_item.id, FeedbackType.FACTUAL_ERROR, reason="陈述有误")

    assert any("已核实" in r for r in excinfo.value.reasons)
    assert db_session.scalars(select(Feedback)).first() is None
    assert noise_item.retracted is False


def test_unknown_item_rejected(db_session) -> None:
    with pytest.raises(FeedbackRejectedError) as excinfo:
        _submit(db_session, 9999, FeedbackType.VALID)

    assert excinfo.value.reasons == ["情报条目不存在"]


@pytest.mark.parametrize(
    ("feedback_type", "expected_channels"),
    [
        (FeedbackType.VALID, frozenset({CREDIT, CONFIGURATION})),
        (FeedbackType.FACTUAL_ERROR, frozenset({DISPOSITION, CREDIT, ITERATION})),
        (FeedbackType.IRRELEVANT, frozenset({CONFIGURATION})),
        (FeedbackType.OUTDATED, frozenset({CONFIGURATION})),
        (FeedbackType.DUPLICATE_NOISE, frozenset({ITERATION})),
        (FeedbackType.RATING_DISPUTE, frozenset({DISPOSITION})),
        (FeedbackType.REVIEW_DISPUTE, frozenset({DISPOSITION, ITERATION})),
    ],
)
def test_routing_table_matches_domain_model(
    feedback_type: FeedbackType, expected_channels: frozenset
) -> None:
    """分流表逐类型对齐领域模型 §6：仅有效 / 事实错误动信用（提交路径见上）。"""
    assert FEEDBACK_ROUTING[feedback_type] == expected_channels
    credit_types = {t for t, channels in FEEDBACK_ROUTING.items() if CREDIT in channels}
    assert credit_types == {FeedbackType.VALID, FeedbackType.FACTUAL_ERROR}


# ---- 审查异议（doc-02 §6 处置 + 迭代通路） ----


@pytest.fixture
def noise_item(db_session) -> IntelligenceItem:
    """预置一条噪音态条目（审查否决产物，异议目标）。"""
    from iih.ledger.models import Medium, Modality

    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    item = IntelligenceItem(
        statement="W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产",
        status=ItemStatus.NOISE,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_review_dispute_lands_and_routes(noise_item, db_session) -> None:
    """异议携理由落账，分流处置（噪音回候选重审）+ 迭代（审查口径调优）。"""
    result = _submit(
        db_session, noise_item.id, FeedbackType.REVIEW_DISPUTE, reason="陈述明确命中需求主题"
    )

    feedback = db_session.get(Feedback, result.feedback_id)
    assert feedback is not None
    assert feedback.reason == "陈述明确命中需求主题"
    assert result.channels == frozenset({DISPOSITION, ITERATION})
    assert result.credit_update is None  # 异议不动信用


def test_review_dispute_without_reason_rejected(noise_item, db_session) -> None:
    """异议理由必填：理由为重审输入。"""
    with pytest.raises(FeedbackRejectedError) as excinfo:
        _submit(db_session, noise_item.id, FeedbackType.REVIEW_DISPUTE)

    assert any("理由" in r for r in excinfo.value.reasons)
    assert db_session.scalars(select(Feedback)).first() is None


def test_review_dispute_rejects_non_noise_item(db_session, verified_item) -> None:
    """异议仅对噪音态条目开放。"""
    with pytest.raises(FeedbackRejectedError) as excinfo:
        _submit(db_session, verified_item.id, FeedbackType.REVIEW_DISPUTE, reason="x")

    assert any("噪音态" in r for r in excinfo.value.reasons)
