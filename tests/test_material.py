"""素材管线单测（IIH-02.01、doc-02 §4.5）：状态推进、待标记门控、逐发言人归因、标记端点。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import unquote, unquote_plus

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from conftest import (
    FakeAsr,
    FakeSnapshotStore,
    _make_dispatch_llm,
    make_fake_llm_manual,
    make_manual_extraction,
)
from iih.agents.collector import AttributionResult, Collector, ManualExtractionResult
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
from iih.tools.asr import relabel_speakers, speaker_hints, split_speakers
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
    """上传 → 提交转写 → 停待标记 → 标记完成 → 抽取落账：Completed、派生、条目挂第三轨。"""
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

    assert outcome == PENDING  # 门控：转写完成停待标记，不自动抽取
    db_session.expire_all()
    material = db_session.get(Material, material.id)
    assert material is not None
    assert material.status is MaterialStatus.TRANSCRIBED

    with factory() as mark_session:  # 模拟标记完成 → 抽取中
        mark_session.execute(
            update(Material)
            .where(Material.id == material.id)
            .values(status=MaterialStatus.EXTRACTING)
        )
        mark_session.commit()
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

    gated = run_pipeline_round(  # 门控：轮询完成停待标记，本轮不抽取
        settings=get_settings(), session_factory=factory, llm=llm, store=store, asr=asr
    )
    assert gated.material_done == 0
    db_session.expire_all()
    assert db_session.get(Material, material.id).status is MaterialStatus.TRANSCRIBED

    with factory() as mark_session:  # 模拟标记完成 → 抽取中
        mark_session.execute(
            update(Material)
            .where(Material.id == material.id)
            .values(status=MaterialStatus.EXTRACTING)
        )
        mark_session.commit()
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


def test_split_speakers_aggregates_by_speaker() -> None:
    """切段：同发言人全局聚合为一段（首现顺序），无前缀归当前段，整稿无前缀单一匿名段。"""
    text = (
        "[00:00] 发言人1：张三第一句\n"
        "接续行\n"
        "[00:30] 发言人2：李四一句\n"
        "[01:00] 发言人1：张三第二句\n"
    )
    assert split_speakers(text) == [
        ("发言人1", "[00:00] 发言人1：张三第一句\n接续行\n[01:00] 发言人1：张三第二句"),
        ("发言人2", "[00:30] 发言人2：李四一句"),
    ]
    assert split_speakers("无前缀整稿") == [("", "无前缀整稿")]


def test_relabel_speakers_replaces_marked_only() -> None:
    """改名：映射内标签替换为实名，映射外保留；时间戳不动。"""
    text = "[00:00] 发言人1：甲发言\n[00:30] 发言人2：乙发言\n"
    relabeled = relabel_speakers(text, {"发言人1": "黄胜"})
    assert relabeled == "[00:00] 黄胜：甲发言\n[00:30] 发言人2：乙发言\n"


def test_speaker_hints_first_utterances() -> None:
    """认人提示：每人前两句发言（去前缀，同人聚合后按序取），超长截断。"""
    text = (
        "[00:00] 发言人1：大家好，今天讨论矿卡\n"
        "[00:30] 发言人2：我先说说出口\n"
        "出口订单排到明年\n"
        "[01:00] 发言人1：国内呢\n"
        "[01:30] 发言人1：第三句不进提示\n"
    )
    assert speaker_hints(text) == {
        "发言人1": "大家好，今天讨论矿卡 / 国内呢",
        "发言人2": "我先说说出口 / 出口订单排到明年",
    }
    assert len(speaker_hints("[00:00] 发言人1：" + "长" * 150)["发言人1"]) == 100


class _SpeakerEchoLlm:
    """prompt-aware 替身：抽取按段逐行出陈述；归因取段内首个发言人标签为信源名。"""

    def __init__(self) -> None:
        self.extraction_calls: list[str] = []
        self.attribution_calls: list[str] = []
        self.chat = SimpleNamespace(completions=_SpeakerEchoCompletions(self))


class _SpeakerEchoCompletions:
    def __init__(self, outer: "_SpeakerEchoLlm") -> None:
        self.outer = outer

    def create_with_completion(self, *, response_model, messages, **kwargs):
        user = next(m["content"] for m in messages if m["role"] == "user")
        if response_model is ManualExtractionResult:
            self.outer.extraction_calls.append(user)
            body = user.split("素材文本：\n", 1)[1]
            result: object = make_manual_extraction(
                *(line.split("：", 1)[1] for line in body.splitlines() if "：" in line)
            )
        else:
            assert response_model is AttributionResult
            self.outer.attribution_calls.append(user)
            body = user.split("陈述：", 1)[1]
            speaker = next(label for label, _ in split_speakers(body) if label)
            result = AttributionResult(
                source_name=speaker,
                source_type="person",
                outlet_name=None,
                rationale=f"段内发言人标签 {speaker}",
            )
        return result, SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def test_submit_material_attributes_per_speaker(db_session) -> None:
    """逐发言人归因：标记实名的转写稿按人切段，各自成源（同人聚合一次归因）。"""
    material = _seed_material(db_session, status=MaterialStatus.EXTRACTING)
    derivation = Derivation(
        material_id=material.id,
        producer=DerivationProducer.TOOL,
        producer_ref="tingwu-offline",
        output_text=(
            "[00:00] 黄胜：三一挖掘机国内销量增长\n"
            "[00:30] 王博：出口订单排到明年\n"
            "[01:00] 黄胜：电动化占比过半\n"
        ),
    )
    db_session.add(derivation)
    db_session.flush()
    llm = _SpeakerEchoLlm()

    proposals = Collector(llm=llm, session=db_session, model="test").submit_material(
        material=material, derivation=derivation
    )

    assert len(llm.extraction_calls) == 2  # 黄胜两行聚合一段、王博一段
    assert len(llm.attribution_calls) == 2
    assert {p.provenance.source_name for p in proposals} == {"黄胜", "王博"}
    assert {p.payload.statement for p in proposals} == {
        "三一挖掘机国内销量增长",
        "电动化占比过半",
        "出口订单排到明年",
    }


def _transcribed_client(db_session, upload_client):
    """推到待标记态：上传 → 转写完成，返回 (client, material_id)。"""
    client, store, asr = upload_client
    client.post(
        "/submissions",
        data={"medium_code": "meeting_discussion"},
        files={"files": ("meeting.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    asr.finish("fake-task-1")
    process_material(
        settings=get_settings(),
        session_factory=client.app.state.session_factory,
        llm=client.app.state.llm,
        asr=asr,
        store=store,
        material_id=db_session.scalars(select(Material.id)).one(),
    )
    db_session.expire_all()
    material = db_session.scalars(select(Material)).one()
    assert material.status is MaterialStatus.TRANSCRIBED
    return client, material.id


def test_mark_speakers_appends_human_derivation(db_session, upload_client) -> None:
    """标记：实名替换转写稿追加人工派生（父级=ASR 派生），状态转抽取中。"""
    client, material_id = _transcribed_client(db_session, upload_client)

    response = client.post(
        f"/materials/{material_id}/mark", data={"发言人1": "黄胜"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert "已标记 1 位发言人" in response.text
    db_session.expire_all()
    material = db_session.get(Material, material_id)
    assert material is not None
    assert material.status is MaterialStatus.EXTRACTING
    derivations = db_session.scalars(
        select(Derivation).where(Derivation.material_id == material_id).order_by(Derivation.id)
    ).all()
    assert [d.producer for d in derivations] == [DerivationProducer.TOOL, DerivationProducer.HUMAN]
    assert derivations[1].parent_id == derivations[0].id
    assert (
        derivations[1].output_text == "[00:00] 黄胜：W 公司与 Z 集团签署合资协议，Q4 设立合资公司"
    )


def test_mark_form_shows_speaker_hints(db_session, upload_client) -> None:
    """标记行上下文：待标记表单每人附其发言片段（认人用，与转写稿并存）。"""
    client, _ = _transcribed_client(db_session, upload_client)

    response = client.get("/submissions")

    assert response.status_code == 200
    assert 'class="markhint"' in response.text
    # 转写稿 pre、title 属性、提示文本各一次
    assert response.text.count("W 公司与 Z 集团签署合资协议") == 3


def test_mark_rejects_blank_and_wrong_state(db_session, upload_client) -> None:
    """标记校验：全空实名拒绝且状态不动；非待标记态拒绝。"""
    client, material_id = _transcribed_client(db_session, upload_client)

    blank = client.post(
        f"/materials/{material_id}/mark", data={"发言人1": " "}, follow_redirects=False
    )
    assert blank.status_code == 303
    assert "未填写任何发言人实名" in unquote(blank.headers["location"])
    db_session.expire_all()
    assert db_session.get(Material, material_id).status is MaterialStatus.TRANSCRIBED

    done = client.post(
        f"/materials/{material_id}/mark", data={"发言人1": "黄胜"}, follow_redirects=True
    )
    assert done.status_code == 200
    db_session.expire_all()
    assert db_session.get(Material, material_id).status is MaterialStatus.EXTRACTING
    again = client.post(
        f"/materials/{material_id}/mark", data={"发言人1": "黄胜"}, follow_redirects=False
    )
    assert again.status_code == 303
    db_session.expire_all()
    assert db_session.get(Material, material_id).status is MaterialStatus.EXTRACTING


def test_mark_requires_all_speakers_named(db_session, upload_client) -> None:
    """强制全量实名：漏标拒绝（报缺谁、状态不动），全标放行。"""
    client, _, _ = upload_client
    material = _seed_material(db_session, status=MaterialStatus.TRANSCRIBED)
    db_session.add(
        Derivation(
            material_id=material.id,
            producer=DerivationProducer.TOOL,
            producer_ref="tingwu-offline",
            output_text="[00:00] 发言人1：甲发言\n[00:30] 发言人2：乙发言\n",
        )
    )
    db_session.flush()

    partial = client.post(
        f"/materials/{material.id}/mark", data={"发言人1": "黄胜"}, follow_redirects=False
    )
    assert partial.status_code == 303
    location = unquote_plus(partial.headers["location"])
    assert "还有 1 位发言人未填实名：发言人2" in location
    db_session.expire_all()
    assert db_session.get(Material, material.id).status is MaterialStatus.TRANSCRIBED

    full = client.post(
        f"/materials/{material.id}/mark",
        data={"发言人1": "黄胜", "发言人2": "主机厂专家"},
        follow_redirects=True,
    )
    assert full.status_code == 200
    assert "已标记 2 位发言人" in full.text
    db_session.expire_all()
    assert db_session.get(Material, material.id).status is MaterialStatus.EXTRACTING
