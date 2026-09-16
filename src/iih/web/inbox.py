"""反馈提交与异议重审编排（doc-02 §6、doc-07 §5）。

收件箱页已下线（IIH-06）：待反馈队列归宿情报条目列表默认视图，反馈入口落条目详情页；
/ 重定向 /items。分发记录未建：待反馈以已核实未作废无反馈条目近似（doc-02 §4.3）。
"""

from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from iih.agents.reviewer import Reviewer
from iih.agents.verifier import Verifier
from iih.config import get_settings
from iih.ledger.feedback_router import TYPE_LABELS, FeedbackRejectedError, FeedbackRouter
from iih.ledger.models import (
    FeedbackType,
    IntelligenceItem,
    ReviewDecisionEnum,
)
from iih.ledger.proposal import ItemReviewDisputePayload, ItemReviewDisputeProposal
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.web.deps import get_llm_client, get_session
from iih.web.flash import redirect_with_flash

router = APIRouter()


@router.get("/")
def home():
    return RedirectResponse("/items", status_code=303)


@router.post("/items/{item_id}/feedback")
def item_feedback(
    item_id: int,
    request: Request,
    feedback_type: str = Form(""),
    reason: str = Form(""),
    session: Session = Depends(get_session),
):
    """反馈提交：反馈路由校验落账并分流（doc-02 §6）；失败回详情页带错误，成功回来源页。

    审查异议（review_dispute）落账后携理由立即重审（doc-02 §6 处置通路）：
    重审通过回候选并即时核实；维持否决保持噪音；异议记录留存供迭代通路。
    LLM 仅异议路径按需构造（其余反馈不依赖智能体，无凭据环境不可因依赖注入失败）。
    """
    item = session.get(IntelligenceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")

    try:
        type_enum = FeedbackType(feedback_type)
    except ValueError:
        return RedirectResponse(
            f"/items/{item_id}?err={quote_plus(f'未知反馈类型：{feedback_type}')}"
            f"&fb_type={quote_plus(feedback_type)}&fb_reason={quote_plus(reason)}",
            status_code=303,
        )

    try:
        FeedbackRouter().submit(
            item_id=item_id, feedback_type=type_enum, reason=reason, session=session
        )
    except FeedbackRejectedError as exc:
        return RedirectResponse(
            f"/items/{item_id}?err={quote_plus('；'.join(exc.reasons))}"
            f"&fb_type={quote_plus(feedback_type)}&fb_reason={quote_plus(reason)}",
            status_code=303,
        )

    if type_enum is FeedbackType.REVIEW_DISPUTE:
        err = _run_dispute_rereview(
            item=item, reason=reason, session=session, llm=get_llm_client(request)
        )
        if err is not None:
            return RedirectResponse(f"/items/{item_id}?err={quote_plus(err)}", status_code=303)
        message = "审查异议已记录并重审"
    else:
        message = f"已记录反馈：{TYPE_LABELS[type_enum]}"

    referer = request.headers.get("referer")
    return redirect_with_flash(referer or f"/items/{item_id}", message)


def _run_dispute_rereview(
    *, item: IntelligenceItem, reason: str, session: Session, llm
) -> str | None:
    """异议重审编排：审查智能体携理由重审 → 异议提案落账 → 通过则即时核实。

    返回错误文案；None 为成功。反馈已落账（异议记录不因重审失败丢失）。
    """
    reviewer = Reviewer(llm=llm, session=session, model=get_settings().llm_model)
    try:
        re_review = reviewer.review(item, dispute_note=reason.strip())
    except Exception as exc:  # LLM 调用失败等
        return f"异议已记录，但重审失败：{exc}"

    try:
        StateMachineExecutor().execute(
            ItemReviewDisputeProposal(
                payload=ItemReviewDisputePayload(
                    item_id=item.id,
                    decision=re_review.payload.decision,
                    reason_type=re_review.payload.reason_type,
                    matched_requirement_id=re_review.payload.matched_requirement_id,
                ),
                rationale=re_review.rationale,
            ),
            session=session,
        )
        if re_review.payload.decision is ReviewDecisionEnum.PASS:
            verification = Verifier(session=session).verify(item)
            StateMachineExecutor().execute(verification, session=session)
    except ProposalRejectedError as exc:
        return f"异议已记录，但重审落账被驳回：{'；'.join(exc.reasons)}"
    except Exception as exc:  # 核实公式异常等
        return f"异议已记录，重审通过但核实失败：{exc}"
    return None
