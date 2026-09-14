"""信用计算器与信用归因（IIH-01.06）：doc-04 §2.3 公式 + decision-04 归因 + 路由内联落账。"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from iih.ledger.credit import (
    HALF_LIFE_DAYS,
    SOURCE_CREDIT_FORMULA_VERSION,
    attribute_responsible_source,
    compute_credit_score,
    score_to_grade,
    source_adjustments,
)
from iih.ledger.feedback_router import FeedbackRouter
from iih.ledger.models import (
    CreditAdjustment,
    Feedback,
    FeedbackType,
    IntelligenceItem,
    ItemMode,
    ItemStatus,
    Medium,
    Modality,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
)

T0 = datetime(2026, 9, 1, tzinfo=UTC)


# ---- 公式（纯函数） ----


def test_score_at_occurrence_full_weight() -> None:
    """发生时点不计衰减：score(t0) = Σ delta。"""
    score = compute_credit_score([(1, T0), (-2, T0)], at=T0)
    assert score == pytest.approx(-1.0)


def test_score_half_life_decay() -> None:
    """180 天半衰期：单次 +1 经 180 天衰减为 0.5。"""
    score = compute_credit_score([(1, T0)], at=T0 + timedelta(days=HALF_LIFE_DAYS))
    assert score == pytest.approx(0.5)


def test_score_sum_with_per_event_decay() -> None:
    """各事件独立衰减：+1（t0）与 −2（t0+90d）在 t0+180d 处合计。"""
    at = T0 + timedelta(days=180)
    score = compute_credit_score([(1, T0), (-2, T0 + timedelta(days=90))], at=at)
    assert score == pytest.approx(0.5 - 2 * 2 ** (-0.5))


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (8.0, "A"),
        (7.999, "B"),
        (4.0, "B"),
        (3.999, "C"),
        (0.0, "C"),
        (-0.001, "D"),
        (-4.0, "D"),
        (-4.001, "E"),
        (-8.0, "E"),
        (-8.001, "F"),
    ],
)
def test_grade_thresholds(score: float, grade: str) -> None:
    """分档阈值（宽容制）：分数区间 → A–F，边界值含左闭右开。"""
    assert score_to_grade(score) == grade


# ---- 归因与路由内联落账 ----


@pytest.fixture
def chain_item(db_session) -> IntelligenceItem:
    """预置已核实条目 + 双节点转引链：W 公司（最早引入）→ 转载资讯站（如实转述）。

    credit_confirmed 参数控制责任信源是否已确认（decision-05）。
    """
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()

    w_outlet = Outlet(name="官网", medium=medium)
    w = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, outlets=[w_outlet])
    re_outlet = Outlet(name="资讯页", medium=medium)
    requoter = Source(name="转载资讯站", type=SourceType.MEDIA, confirmed=True, outlets=[re_outlet])

    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.VERIFIED,
        rating="B2",
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 1, tzinfo=UTC),
        original_snapshot="W 公司今日公告，与 Z 集团签署合资协议。",
        source=w,
        outlet=w_outlet,
    )
    db_session.add_all(
        [
            item,
            ProvenanceChainNode(
                item=item,
                source=w,
                outlet=w_outlet,
                modality=modality,
                medium=medium,
                collected_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
            ProvenanceChainNode(
                item=item,
                source=requoter,
                outlet=re_outlet,
                modality=modality,
                medium=medium,
                collected_at=datetime(2026, 9, 5, tzinfo=UTC),
            ),
        ]
    )
    db_session.flush()
    return item


@pytest.fixture
def unconfirmed_chain_item(db_session, chain_item) -> IntelligenceItem:
    """责任信源待确认：不入正式池、不参与信用记账（decision-05）。"""
    chain_item.source.confirmed = False
    db_session.flush()
    return chain_item


def _submit(db_session, item_id: int, feedback_type: FeedbackType, reason: str = ""):
    return FeedbackRouter().submit(
        item_id=item_id, feedback_type=feedback_type, reason=reason, session=db_session
    )


def _source_by_name(db_session, name: str) -> Source:
    return db_session.scalars(select(Source).where(Source.name == name)).one()


def test_attribution_picks_earliest_chain_source(db_session, chain_item) -> None:
    """归因（decision-04）：责任信源 = 转引链最早引入陈述的信源，非转载站。"""
    responsible = attribute_responsible_source(db_session, chain_item)
    assert responsible is not None
    assert responsible.name == "W 公司"


def test_attribution_skips_unconfirmed_source(db_session, unconfirmed_chain_item) -> None:
    responsible = attribute_responsible_source(db_session, unconfirmed_chain_item)
    assert responsible is None


def test_valid_feedback_updates_credit_and_leaves_requoter_untouched(
    db_session, chain_item
) -> None:
    """AC#1：「有效」→ 责任信源 +1 首评落 C 档；如实转载者不动。"""
    result = _submit(db_session, chain_item.id, FeedbackType.VALID)

    w = _source_by_name(db_session, "W 公司")
    assert result.credit_update is not None
    assert result.credit_update.delta == 1
    assert result.credit_update.grade_after == "C"
    assert w.credit == "C"

    adjustment = db_session.scalars(select(CreditAdjustment)).unique().one()
    assert adjustment.source_id == w.id
    assert adjustment.feedback_id == result.feedback_id
    assert adjustment.delta == 1
    assert adjustment.score_after == pytest.approx(1.0)
    assert adjustment.grade_after == "C"
    assert adjustment.formula_version == SOURCE_CREDIT_FORMULA_VERSION

    requoter = _source_by_name(db_session, "转载资讯站")
    assert requoter.credit is None  # 如实转述者不受奖惩
    assert len(source_adjustments(db_session, requoter.id)) == 0


def test_factual_error_penalty_and_retraction(db_session, chain_item) -> None:
    """AC#2：「事实错误」→ 责任信源 −2 落 D 档；条目作废标记落账。"""
    result = _submit(db_session, chain_item.id, FeedbackType.FACTUAL_ERROR, reason="协议从未签署")

    w = _source_by_name(db_session, "W 公司")
    assert result.credit_update is not None
    assert result.credit_update.delta == -2
    assert result.credit_update.grade_after == "D"
    assert w.credit == "D"

    db_session.refresh(chain_item)
    assert chain_item.retracted is True


def test_unconfirmed_source_skips_credit_but_feedback_lands(
    db_session, unconfirmed_chain_item
) -> None:
    """待确认信源不参与信用记账（decision-05）：反馈照常落账、信用通路跳过、作废照打。"""
    result = _submit(
        db_session, unconfirmed_chain_item.id, FeedbackType.FACTUAL_ERROR, reason="协议从未签署"
    )

    assert result.credit_update is None
    assert db_session.scalars(select(CreditAdjustment)).unique().first() is None
    feedback = db_session.get(Feedback, result.feedback_id)
    assert feedback is not None
    db_session.refresh(unconfirmed_chain_item)
    assert unconfirmed_chain_item.retracted is True


def test_non_credit_feedback_type_no_adjustment(db_session, chain_item) -> None:
    """非信用通路反馈（如「不相关」）不产生信用调整。"""
    _submit(db_session, chain_item.id, FeedbackType.IRRELEVANT)

    assert db_session.scalars(select(CreditAdjustment)).unique().first() is None
    assert _source_by_name(db_session, "W 公司").credit is None


def test_replay_from_history_reproduces_credit(db_session, chain_item) -> None:
    """AC#3 可重放：同反馈历史重放信用计算 → 与落账快照同分数、同分档。"""
    _submit(db_session, chain_item.id, FeedbackType.VALID)
    _submit(db_session, chain_item.id, FeedbackType.FACTUAL_ERROR, reason="协议从未签署")

    w = _source_by_name(db_session, "W 公司")
    adjustments = source_adjustments(db_session, w.id)
    assert len(adjustments) == 2

    replayed_score = compute_credit_score(
        [(adj.delta, adj.created_at) for adj in adjustments],
        at=adjustments[-1].created_at,
    )
    assert replayed_score == pytest.approx(adjustments[-1].score_after)
    assert score_to_grade(replayed_score) == adjustments[-1].grade_after == w.credit
