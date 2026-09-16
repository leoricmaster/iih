"""素材管线单测（IIH-02.01、doc-02 §4.5）：状态推进、失败留痕、重试上限、上传与人工重试端点。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from conftest import (
    FakeAsr,
    FakeSnapshotStore,
    _make_dispatch_llm,
    make_fake_llm_manual,
    make_manual_extraction,
)
from iih.agents.collector import AttributionResult, ManualExtractionResult
from iih.agents.reviewer import ReviewJudgmentResult
from iih.config import get_settings
from iih.ledger.models import (
    Derivation,
    DerivationProducer,
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    Material,
    MaterialStatus,
    Medium,
    Modality,
)
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    ProvenanceData,
)
from iih.ledger.state_machine import ProposalRejectedError, StateMachineExecutor
from iih.pipeline import DONE, FAILED, PENDING, process_material, run_pipeline_round
from iih.web.app import create_app
from iih.web.deps import get_session


def _seed_material(db_session, *, status=MaterialStatus.UPLOADED, retry_count=0) -> Material:
    medium = db_session.scalars(select(Medium).where(Medium.code == "meeting_discussion")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "audio")).one()
    store = FakeSnapshotStore()
    material = Material(
        modality_id=modality.id,
        medium_id=medium.id,
        collected_at=datetime.now(UTC),
        object_key=store.put_material(b"fake-audio-bytes", "mp3"),
        filename="meeting.mp3",
        status=status,
        retry_count=retry_count,
    )
    db_session.add(material)
    db_session.flush()
    return material


def _session_factory(db_session):
    return sessionmaker(bind=db_session.bind, join_transaction_mode="create_savepoint")


def test_material_lifecycle_submit_poll_extract(db_session, w_attribution) -> None:
    """上传 → 提交转写 → 轮询完成 → 抽取落账：素材 Completed、派生转写稿、条目挂第三轨。"""
    material = _seed_material(db_session)
    store = FakeSnapshotStore()
    store.materials[material.object_key] = b"fake-audio-bytes"
    asr = FakeAsr()
    llm = make_fake_llm_manual(
        make_manual_extraction("W 公司与 Z 集团签署合资协议，Q4 设立合资公司"), w_attribution
    )
    factory = _session_factory(db_session)

    outcome = process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=llm,
        asr=asr,
        store=store,
        material_id=material.id,
    )

    assert outcome == PENDING
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.PROCESSING
    assert material.external_task_id == "fake-task-1"
    assert asr.submitted == [b"fake-audio-bytes"]

    asr.finish("fake-task-1")
    outcome = process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=llm,
        asr=asr,
        store=store,
        material_id=material.id,
    )

    assert outcome == DONE
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.COMPLETED
    assert material.retry_count == 0
    derivation = db_session.scalars(
        select(Derivation).where(Derivation.material_id == material.id)
    ).one()
    assert derivation.producer is DerivationProducer.TOOL
    assert derivation.output_text == asr.transcript
    assert derivation.duration_seconds == 300
    item = db_session.scalars(select(IntelligenceItem)).one()
    assert item.status is ItemStatus.LEAD
    assert item.material_id == material.id
    assert item.derivation_id == derivation.id
    assert item.source is not None and item.source.name == "W 公司"


def test_material_submit_failure_leaves_trace(db_session) -> None:
    """AC#2：转写提交失败留痕（状态 + 原因 + 重试计数），不静默。"""
    material = _seed_material(db_session)
    store = FakeSnapshotStore()
    store.materials[material.object_key] = b"fake-audio-bytes"

    outcome = process_material(
        settings=get_settings(),
        session_factory=_session_factory(db_session),
        llm=object(),
        asr=FakeAsr(submit_error="OSS 中转上传失败"),
        store=store,
        material_id=material.id,
    )

    assert outcome == FAILED
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.PROCESS_FAILED
    assert "OSS 中转上传失败" in (material.failure_reason or "")
    assert material.retry_count == 1


def test_material_check_failure_leaves_trace(db_session) -> None:
    """AC#2：转写任务查询失败留痕，可被循环自动重试。"""
    material = _seed_material(db_session)
    store = FakeSnapshotStore()
    store.materials[material.object_key] = b"fake-audio-bytes"
    asr = FakeAsr()
    factory = _session_factory(db_session)
    process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=object(),
        asr=asr,
        store=store,
        material_id=material.id,
    )

    asr.check_error = "听悟任务查询失败"
    outcome = process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=object(),
        asr=asr,
        store=store,
        material_id=material.id,
    )

    assert outcome == FAILED
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.PROCESS_FAILED
    assert "听悟任务查询失败" in (material.failure_reason or "")


def test_material_failure_retries_then_caps(db_session) -> None:
    """失败自动重试直至上限（MAX_MATERIAL_RETRIES=3），达上限转人工（不再提交）。"""
    material = _seed_material(db_session)
    store = FakeSnapshotStore()
    store.materials[material.object_key] = b"fake-audio-bytes"
    asr = FakeAsr(submit_error="持续失败")
    factory = _session_factory(db_session)

    for _ in range(3):
        process_material(
            settings=get_settings(),
            session_factory=factory,
            llm=object(),
            asr=asr,
            store=store,
            material_id=material.id,
        )

    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.retry_count == 3

    outcome = process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=object(),
        asr=asr,
        store=store,
        material_id=material.id,
    )
    assert outcome == PENDING
    assert len(asr.attempts) == 3  # 达上限后不再提交
    assert asr.submitted == []


def test_material_zero_statements_still_completes(db_session, w_attribution) -> None:
    """零陈述亦完成留痕：素材 Completed、无条目（不产半成品也不卡死）。"""
    material = _seed_material(db_session, status=MaterialStatus.EXTRACTING)
    derivation = Derivation(
        material_id=material.id,
        producer=DerivationProducer.TOOL,
        producer_ref="tingwu-offline",
        output_text="[00:00] 发言人1：寒暄问候",
    )
    db_session.add(derivation)
    db_session.flush()
    llm = make_fake_llm_manual(ManualExtractionResult(statements=[]), w_attribution)

    outcome = process_material(
        settings=get_settings(),
        session_factory=_session_factory(db_session),
        llm=llm,
        asr=FakeAsr(),
        store=FakeSnapshotStore(),
        material_id=material.id,
    )

    assert outcome == DONE
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.COMPLETED
    assert db_session.scalars(select(IntelligenceItem)).all() == []


def test_material_stage_skips_without_asr(db_session) -> None:
    """ASR 未配置：素材段整体跳过，素材留队不失败。"""
    from iih.pipeline import run_material_stage

    material = _seed_material(db_session)

    run_material_stage(
        settings=get_settings(),
        session_factory=_session_factory(db_session),
        llm=object(),
        asr=None,
        store=FakeSnapshotStore(),
    )

    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.UPLOADED


def test_pipeline_round_counts_material_done(db_session, w_attribution) -> None:
    """完整一轮含素材段：转写完成的素材计入 material_done，全链无错误。"""
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    db_session.add(ir)
    db_session.flush()
    material = _seed_material(db_session)
    store = FakeSnapshotStore()
    store.materials[material.object_key] = b"fake-audio-bytes"
    asr = FakeAsr()
    llm = _make_dispatch_llm(
        {
            ManualExtractionResult: make_manual_extraction("W 公司与 Z 集团签署合资协议"),
            AttributionResult: w_attribution,
            ReviewJudgmentResult: ReviewJudgmentResult(
                decision="pass",
                reason_type=None,
                matched_requirement_id=ir.id,
                rationale="陈述主题命中激活需求「跟踪 W 公司」",
            ),
        },
        prompt_tokens=10,
        completion_tokens=5,
    )
    factory = _session_factory(db_session)
    process_material(
        settings=get_settings(),
        session_factory=factory,
        llm=llm,
        asr=asr,
        store=store,
        material_id=material.id,
    )
    asr.finish("fake-task-1")

    summary = run_pipeline_round(
        settings=get_settings(), session_factory=factory, llm=llm, store=store, asr=asr
    )

    assert summary.material_done == 1
    assert summary.material_failed == 0
    assert "素材 1（完成 1、失败 0）" in summary.flash()
    assert summary.errors == []


def _third_track_payload(
    material: Material, derivation: Derivation | None
) -> IntelligenceItemNewProposal:
    return IntelligenceItemNewProposal(
        payload=IntelligenceItemNewPayload(
            statement="W 公司与 Z 集团签署合资协议，Q4 设立合资公司",
            mode=ItemMode.MANUAL,
            content_fingerprint="fp-third-track",
            material_id=material.id,
            derivation_id=derivation.id if derivation else None,
        ),
        provenance=ProvenanceData(
            modality_code="audio",
            medium_code="meeting_discussion",
            collected_at=datetime.now(UTC),
            source_name="W 公司",
            source_type="company",
            outlet_name=None,
        ),
        rationale="转写稿抽取",
    )


def test_item_new_accepts_material_track(db_session) -> None:
    """第三轨：条目挂素材 + 派生级（无内嵌快照）亦通过完整性校验落账。"""
    material = _seed_material(db_session)
    derivation = Derivation(
        material_id=material.id,
        producer=DerivationProducer.TOOL,
        producer_ref="tingwu-offline",
        output_text="[00:00] 发言人1：发言",
    )
    db_session.add(derivation)
    db_session.flush()

    StateMachineExecutor().execute(_third_track_payload(material, derivation), session=db_session)

    item = db_session.scalars(select(IntelligenceItem)).one()
    assert item.material_id == material.id
    assert item.derivation_id == derivation.id
    assert item.original_snapshot is None


def test_item_new_rejects_derivation_of_other_material(db_session) -> None:
    """派生级不属于所挂素材：驳回（无溯源不落账）。"""
    material = _seed_material(db_session)
    other = _seed_material(db_session)
    derivation = Derivation(
        material_id=other.id,
        producer=DerivationProducer.TOOL,
        producer_ref="tingwu-offline",
        output_text="[00:00] 发言人2：发言",
    )
    db_session.add(derivation)
    db_session.flush()

    with pytest.raises(ProposalRejectedError):
        StateMachineExecutor().execute(
            _third_track_payload(material, derivation), session=db_session
        )


def test_item_new_rejects_material_without_derivation(db_session) -> None:
    """挂素材但缺派生级：完整性校验驳回。"""
    material = _seed_material(db_session)

    with pytest.raises(ProposalRejectedError):
        StateMachineExecutor().execute(_third_track_payload(material, None), session=db_session)


@pytest.fixture
def upload_client(db_session, monkeypatch, w_attribution):
    app = create_app()
    app.state.llm = make_fake_llm_manual(
        make_manual_extraction("W 公司与 Z 集团签署合资协议"), w_attribution
    )
    app.dependency_overrides[get_session] = lambda: db_session
    store = FakeSnapshotStore()
    asr = FakeAsr()
    monkeypatch.setattr("iih.web.submissions.make_snapshot_store", lambda _s: store)
    monkeypatch.setattr("iih.web.submissions.make_tingwu_asr", lambda _s: asr)
    with TestClient(app) as client:
        app.state.session_factory = _session_factory(db_session)  # lifespan 后再替换测试工厂
        yield client, store, asr


def test_upload_recording_submits_transcription(db_session, upload_client) -> None:
    """AC#1：上传录音即建素材并即时提交转写（事件驱动优先）。"""
    client, store, asr = upload_client

    response = client.post(
        "/submissions",
        data={"medium_code": "meeting_discussion"},
        files={"files": ("meeting.mp3", b"fake-audio-bytes", "audio/mpeg")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "录音已上传" in response.text
    db_session.expire_all()
    material = db_session.scalars(select(Material)).one()
    assert material.status is MaterialStatus.PROCESSING
    assert material.external_task_id == "fake-task-1"
    assert store.materials[material.object_key] == b"fake-audio-bytes"
    assert asr.submitted == [b"fake-audio-bytes"]


def test_upload_rejects_non_audio(db_session, upload_client) -> None:
    client, _, asr = upload_client

    response = client.post(
        "/submissions",
        data={"medium_code": "meeting_discussion"},
        files={"files": ("notes.txt", b"plain text", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "仅支持音频文件" in response.text
    assert asr.submitted == []
    assert db_session.scalars(select(Material)).all() == []


def test_upload_rejects_when_asr_unconfigured(db_session, monkeypatch) -> None:
    monkeypatch.setattr("iih.web.submissions.make_tingwu_asr", lambda _s: None)
    monkeypatch.setattr("iih.web.submissions.make_snapshot_store", lambda _s: FakeSnapshotStore())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        app.state.session_factory = _session_factory(db_session)
        response = client.post(
            "/submissions",
            data={"medium_code": "meeting_discussion"},
            files={"files": ("meeting.mp3", b"fake-audio-bytes", "audio/mpeg")},
            follow_redirects=True,
        )

    assert "听悟 ASR 未配置" in response.text
    assert db_session.scalars(select(Material)).all() == []


def test_retry_material_resets_and_resubmits(db_session, upload_client) -> None:
    """人工重试：清计数与原因后重新提交（达上限转人工的人口）。"""
    client, _, asr = upload_client
    asr.submit_error = "先失败一次"
    client.post(
        "/submissions",
        data={"medium_code": "meeting_discussion"},
        files={"files": ("meeting.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    db_session.expire_all()
    material = db_session.scalars(select(Material)).one()
    assert material.status is MaterialStatus.PROCESS_FAILED

    asr.submit_error = ""
    response = client.post(f"/materials/{material.id}/retry", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.PROCESSING
    assert material.failure_reason is None
    assert material.retry_count == 0
    assert len(asr.submitted) == 1


def test_round_summary_flash_includes_material_part() -> None:
    """flash 摘要：有素材活动才追加素材段（无素材活动不加）。"""
    from iih.pipeline import RoundSummary

    idle = RoundSummary().flash()
    assert "素材" not in idle

    active = RoundSummary(material_done=2, material_failed=1).flash()
    assert "素材 3（完成 2、失败 1）" in active
