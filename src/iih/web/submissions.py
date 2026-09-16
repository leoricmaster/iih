"""录入素材页（doc-07 §2.3、原型）：贴文字纪要或上传录音，抽取陈述落账为线索。"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates
from instructor import Instructor
from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session, selectinload

from iih.agents.collector import Collector
from iih.config import get_settings
from iih.ledger.models import (
    IntelligenceItem,
    ItemMode,
    Material,
    MaterialStatus,
    Medium,
    Modality,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.pipeline import process_material
from iih.tools.asr import make_tingwu_asr
from iih.tools.snapshot_store import make_snapshot_store
from iih.web.context import STATUS_LABELS, base_context, register_template_filters
from iih.web.deps import get_llm_client, get_session
from iih.web.flash import redirect_with_flash

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = register_template_filters(Jinja2Templates(directory=TEMPLATES_DIR))

router = APIRouter()

RECENT_LIMIT = 10

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "ogg", "opus", "flac", "amr"}

MATERIAL_STATUS_LABELS = {
    MaterialStatus.UPLOADED: "待加工",
    MaterialStatus.PROCESSING: "转写中",
    MaterialStatus.EXTRACTING: "抽取中",
    MaterialStatus.COMPLETED: "已完成",
    MaterialStatus.PROCESS_FAILED: "转写失败",
    MaterialStatus.EXTRACT_FAILED: "抽取失败",
}


def _offline_mediums(session: Session) -> list[Medium]:
    """媒介下拉封闭集合；互联网为自动拉取、不经本页（doc-07 §2.3）。"""
    return list(
        session.scalars(select(Medium).where(Medium.code != "internet").order_by(Medium.id))
    )


def _recent_manual_items(session: Session) -> list[IntelligenceItem]:
    return list(
        session.scalars(
            select(IntelligenceItem)
            .where(IntelligenceItem.mode == ItemMode.MANUAL)
            .order_by(IntelligenceItem.created_at.desc(), IntelligenceItem.id.desc())
            .limit(RECENT_LIMIT)
        )
    )


def _recent_materials(session: Session) -> list[Material]:
    return list(
        session.scalars(
            select(Material)
            .options(selectinload(Material.medium))
            .order_by(Material.collected_at.desc(), Material.id.desc())
            .limit(RECENT_LIMIT)
        )
    )


def _kickoff(request: Request, material_id: int, asr, store) -> None:
    """即时推进一步（事件驱动优先）：失败不阻断，循环兜底自动重试。"""
    try:
        process_material(
            settings=get_settings(),
            session_factory=request.app.state.session_factory,
            llm=None,  # 上传/重试只走提交段，不调抽取 LLM
            asr=asr,
            store=store,
            material_id=material_id,
        )
    except Exception:
        pass


def _render(
    request: Request,
    session: Session,
    errors: list[str] | None = None,
    flash: str = "",
    form_medium: str = "",
    form_statement: str = "",
):
    return templates.TemplateResponse(
        request,
        "submissions.html",
        {
            **base_context(session, "submit"),
            "mediums": _offline_mediums(session),
            "items": _recent_manual_items(session),
            "materials": _recent_materials(session),
            "status_labels": STATUS_LABELS,
            "material_status_labels": MATERIAL_STATUS_LABELS,
            "errors": errors or [],
            "flash": flash,
            "form_medium": form_medium,
            "form_statement": form_statement,
        },
    )


@router.get("/submissions")
def submissions_page(request: Request, flash: str = "", session: Session = Depends(get_session)):
    return _render(request, session, flash=flash)


@router.post("/submissions")
def submit(
    request: Request,
    medium_code: str = Form(""),
    statement: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
    llm: Instructor = Depends(get_llm_client),
):
    """统一提交（原型「提交素材」box）：文字纪要走抽取落账，音频附件建素材即时提交转写。"""

    def fail(reasons: list[str]):
        return _render(request, session, reasons, form_medium=medium_code, form_statement=statement)

    uploads = [f for f in files if f is not None and (f.filename or "").strip()]
    text = statement.strip()
    errors: list[str] = []
    if not medium_code:
        errors.append("请选择媒介")
    bad = [
        f for f in uploads if (f.filename or "").rsplit(".", 1)[-1].lower() not in AUDIO_EXTENSIONS
    ]
    if bad:
        errors.append("仅支持音频文件（图片 / 文档暂不支持）")
    if not text and not uploads:
        errors.append("请上传附件，或填写文字纪要")
    if not errors and medium_code == "internet":
        errors.append("互联网媒介为自动拉取，不经本页录入")
    asr = make_tingwu_asr(get_settings())
    if not errors and uploads and asr is None:
        errors.append("听悟 ASR 未配置，暂不能接收录音")

    if errors:
        return fail(errors)

    messages: list[str] = []

    if uploads:
        medium = session.scalars(select(Medium).where(Medium.code == medium_code)).first()
        modality = session.scalars(select(Modality).where(Modality.code == "audio")).first()
        if medium is None or modality is None:
            return fail(["媒介不存在"])
        store = make_snapshot_store(get_settings())
        for upload in uploads:
            filename = upload.filename or ""
            ext = filename.rsplit(".", 1)[-1].lower()
            material = Material(
                modality_id=modality.id,
                medium_id=medium.id,
                collected_at=datetime.now(UTC),
                object_key=store.put_material(upload.file.read(), ext),
                filename=filename[:500],
                status=MaterialStatus.UPLOADED,
            )
            session.add(material)
            session.commit()
            _kickoff(request, material.id, asr, store)
        messages.append(f"录音已上传 {len(uploads)} 个，转写中")

    if text:
        collector = Collector(llm=llm, session=session, model=get_settings().llm_model)
        try:
            proposals = collector.submit_manual(medium_code=medium_code, statement=text)
        except ValueError as exc:
            return fail([str(exc)])
        if not proposals:
            return fail(["未能从提交文本中识别出情报陈述"])

        created = 0
        failed = 0
        reject_reasons: list[str] = []
        for proposal in proposals:
            try:
                StateMachineExecutor().execute(proposal, session=session)
                created += 1
            except ProposalRejectedError as exc:
                failed += 1
                reject_reasons.extend(exc.reasons)
        if not created:
            return fail(reject_reasons or ["落账失败"])

        message = f"已提交：抽取陈述 {created} 条，进入流水线"
        if failed:
            message += f"；{failed} 条落账失败"
        messages.append(message)

    return redirect_with_flash("/submissions", "；".join(messages))


@router.post("/materials/{material_id}/retry")
def retry_material(material_id: int, request: Request, session: Session = Depends(get_session)):
    """人工重试：清重试计数与失败原因，交回循环自动推进（达上限转人工后的人口）。"""
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(Material)
            .where(
                Material.id == material_id,
                Material.status.in_((MaterialStatus.PROCESS_FAILED, MaterialStatus.EXTRACT_FAILED)),
            )
            .values(retry_count=0, failure_reason=None)
        ),
    )
    session.commit()
    if result.rowcount != 1:
        return redirect_with_flash("/submissions", "素材不在失败态，无需重试")

    settings = get_settings()
    asr = make_tingwu_asr(settings)
    if asr is not None:
        _kickoff(request, material_id, asr, make_snapshot_store(settings))
    return redirect_with_flash("/submissions", "已重试")
