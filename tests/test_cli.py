"""CLI 端到端集成测试（IIH-01.08 AC#1/#2、IIH-01.02 AC#1/#2）。

通过直接调 iih.cli.main(argv=[...]) 跑子命令；mock fetcher 与 LLM。
"""

from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import select

from conftest import make_fake_llm_extraction, make_fake_llm_review
from iih.cli import main
from iih.ledger.models import (
    IntelligenceItem,
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    ItemMode,
    ItemStatus,
    LlmCall,
    Medium,
    Modality,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
    VerificationOutcome,
    VerificationRecord,
)
from iih.ledger.state_machine import StateMachineExecutor

HTML_W = """
<html><body>
  <nav>导航</nav>
  <main><p>W 公司公告：与 Z 集团签署合资协议，Q4 设立合资公司。</p></main>
  <footer>页脚</footer>
</body></html>
"""


def _seed(db_session) -> None:
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True)
    outlet = Outlet(
        source=source, name="官网", entry="https://w-mining.example/news", medium=medium
    )
    db_session.add_all([source, outlet])
    db_session.flush()


def _seed_active_ir(db_session) -> IntelligenceRequirement:
    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题：矿卡、订单、战略",
        status=IntelligenceRequirementStatus.ACTIVE,
    )
    db_session.add(ir)
    db_session.flush()
    return ir


def test_ir_create_then_activate_then_collect_produces_lead(db_session, w_extraction) -> None:
    """支撑 IIH-01.08 AC#1：登记→激活→拉取产出线索，溯源五要素齐备。

    直接走提案路径模拟 CLI 行为（与单元测试一致），collect 链路 mock fetcher 与 LLM。
    """
    _seed(db_session)
    fake_llm = make_fake_llm_extraction(w_extraction)

    # ir-create 等价：登记 Draft
    from iih.ledger.proposal import (
        IntelligenceRequirementActivatePayload,
        IntelligenceRequirementActivateProposal,
        IntelligenceRequirementRegisterPayload,
        IntelligenceRequirementRegisterProposal,
    )

    StateMachineExecutor().execute(
        IntelligenceRequirementRegisterProposal(
            payload=IntelligenceRequirementRegisterPayload(
                name="跟踪 W 公司", content_spec="主题：矿卡"
            ),
            rationale="CLI 登记",
        ),
        session=db_session,
    )
    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert ir.status is IntelligenceRequirementStatus.DRAFT

    # ir-activate 等价：Draft → Active
    StateMachineExecutor().execute(
        IntelligenceRequirementActivateProposal(
            payload=IntelligenceRequirementActivatePayload(requirement_id=ir.id),
            rationale="CLI 激活",
        ),
        session=db_session,
    )
    assert (
        db_session.get(IntelligenceRequirement, ir.id).status
        is IntelligenceRequirementStatus.ACTIVE
    )

    # collect：Director→fetcher→Collector→executor 链路
    from iih.agents.collector import Collector
    from iih.agents.director import Director

    tasks = Director(db_session).propose_tasks()
    assert len(tasks) == 1
    assert tasks[0].source_name == "W 公司"
    assert tasks[0].outlet_name == "官网"
    assert tasks[0].url == "https://w-mining.example/news"

    # mock fetcher 直接返回 HTML（不真发 HTTP）
    with patch("iih.tools.fetcher.httpx.Client") as mock_client_cls:
        client = mock_client_cls.return_value.__enter__.return_value
        import httpx

        client.get.return_value = httpx.Response(
            200, text=HTML_W, request=httpx.Request("GET", "https://w-mining.example/news")
        )

        collector = Collector(llm=fake_llm, session=db_session, model="deepseek-chat")
        proposal = collector.collect_outlet(task=tasks[0], html=HTML_W)

    assert proposal is not None
    result = StateMachineExecutor().execute(proposal, session=db_session)

    item = db_session.get(IntelligenceItem, result.item_id)
    assert item is not None
    assert item.status is ItemStatus.LEAD
    assert item.mode is ItemMode.AUTOMATED
    assert item.statement == w_extraction.statement
    assert item.modality.code == "webpage"
    assert item.medium.code == "internet"
    assert item.source.name == "W 公司"
    assert item.source.confirmed is True
    assert item.outlet.name == "官网"
    assert item.original_url == "https://w-mining.example/news"
    assert item.content_fingerprint is not None and len(item.content_fingerprint) == 64

    # 初始转引链节点
    nodes = db_session.scalars(
        select(ProvenanceChainNode).where(ProvenanceChainNode.item_id == item.id)
    ).all()
    assert len(nodes) == 1
    assert nodes[0].source.name == "W 公司"

    # LLM 计量
    calls = db_session.scalars(select(LlmCall)).all()
    assert len(calls) == 1
    assert calls[0].target == "outlet_collection"


def test_collect_with_duplicate_content_appends_provenance_node(db_session, w_extraction) -> None:
    """支撑 IIH-01.08 AC#2：指纹命中→追加转引链节点，不新建条目、不调 LLM。"""
    _seed(db_session)
    _seed_active_ir(db_session)

    from iih.agents.collector import Collector
    from iih.agents.director import CollectionTask, Director

    tasks = Director(db_session).propose_tasks()
    fake_llm = make_fake_llm_extraction(w_extraction)
    collector = Collector(llm=fake_llm, session=db_session, model="deepseek-chat")

    # 首次拉取：新建条目
    first = collector.collect_outlet(task=tasks[0], html=HTML_W)
    assert first is not None
    StateMachineExecutor().execute(first, session=db_session)
    items_after_first = len(db_session.scalars(select(IntelligenceItem)).all())
    llm_calls_after_first = len(db_session.scalars(select(LlmCall)).all())

    # 第二次拉取同内容（模拟另一信源转载同公告）：指纹命中
    media_source = Source(name="行业媒体 A", type=SourceType.MEDIA, confirmed=True)
    db_session.add(media_source)
    db_session.flush()
    repost_task = CollectionTask(
        requirement_id=tasks[0].requirement_id,
        requirement_name=tasks[0].requirement_name,
        outlet_id=tasks[0].outlet_id,
        source_id=media_source.id,
        source_name="行业媒体 A",
        source_type=SourceType.MEDIA,
        outlet_name=None,
        url="https://media-a.example/repost",
    )

    proposal = collector.collect_outlet(task=repost_task, html=HTML_W)

    from iih.ledger.proposal import ItemProvenanceAppendProposal

    assert isinstance(proposal, ItemProvenanceAppendProposal)
    StateMachineExecutor().execute(proposal, session=db_session)

    # 不新建条目
    assert len(db_session.scalars(select(IntelligenceItem)).all()) == items_after_first
    # 不调 LLM
    assert len(db_session.scalars(select(LlmCall)).all()) == llm_calls_after_first

    # 转引链节点追加
    nodes = db_session.scalars(select(ProvenanceChainNode)).all()
    assert len(nodes) == 2
    appended = next(n for n in nodes if n.source.name == "行业媒体 A")
    assert appended.original_url == "https://media-a.example/repost"


def test_cli_main_ir_create_requires_args() -> None:
    """CLI argparse 校验：ir-create 缺 --name/--spec 时退出非零。"""
    import pytest

    with pytest.raises(SystemExit):
        main(["ir-create"])


def test_cli_ir_create_e2e_lands_draft(db_session, monkeypatch) -> None:
    """ir-create 子命令端到端：CLI argparse → 提案 → 状态机 → 落账 Draft。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.ir.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.ir.make_session_factory", lambda engine: fake_factory)

    rc = main(["ir-create", "--name", "跟踪 W 公司", "--spec", "主题：矿卡"])

    assert rc == 0
    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    assert ir.name == "跟踪 W 公司"
    assert ir.content_spec == "主题：矿卡"
    assert ir.status is IntelligenceRequirementStatus.DRAFT


def test_cli_ir_activate_e2e_transitions_to_active(db_session, monkeypatch) -> None:
    """ir-activate 子命令端到端：Draft → Active。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    ir = IntelligenceRequirement(
        name="跟踪 W 公司",
        content_spec="主题",
        status=IntelligenceRequirementStatus.DRAFT,
    )
    db_session.add(ir)
    db_session.flush()

    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.ir.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.ir.make_session_factory", lambda engine: fake_factory)

    rc = main(["ir-activate", str(ir.id)])

    assert rc == 0
    assert (
        db_session.get(IntelligenceRequirement, ir.id).status
        is IntelligenceRequirementStatus.ACTIVE
    )


def test_cli_collect_e2e_produces_lead(db_session, monkeypatch, w_extraction) -> None:
    """collect 子命令端到端：Director→fetcher→Collector→executor 链路。

    mock fetcher 返回 HTML、LLM 客户端工厂返回替身；session_factory 复用 db_session。
    """
    from contextlib import contextmanager
    from types import SimpleNamespace

    _seed(db_session)
    _seed_active_ir(db_session)

    fake_engine = SimpleNamespace(dispose=lambda: None)
    fake_llm = make_fake_llm_extraction(w_extraction)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.collect.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.collect.make_session_factory", lambda engine: fake_factory)
    monkeypatch.setattr("iih.cli.collect.make_llm_client", lambda settings: fake_llm)
    monkeypatch.setattr("iih.cli.collect.fetch", lambda url, **kwargs: HTML_W)

    rc = main(["collect"])

    assert rc == 0
    item = db_session.scalars(
        select(IntelligenceItem).where(IntelligenceItem.mode == ItemMode.AUTOMATED)
    ).one()
    assert item.status is ItemStatus.LEAD
    assert item.source.name == "W 公司"
    assert item.outlet.name == "官网"
    assert item.original_url == "https://w-mining.example/news"


# ---- IIH-01.02 线索审查过滤 CLI ----


def _seed_lead_for_review(db_session) -> IntelligenceItem:
    """预置一条 Lead 态条目 + 激活 IR（复用 _seed 与 _seed_active_ir）。"""
    _seed(db_session)
    _seed_active_ir(db_session)
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    source = db_session.scalars(select(Source).where(Source.name == "W 公司")).one()
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.LEAD,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=db_session.scalars(select(Modality).where(Modality.code == "webpage")).one(),
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
        content_fingerprint="z" * 64,
        original_url="https://w-mining.example/news",
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_cli_review_e2e_pass_transitions_to_candidate(
    db_session, monkeypatch, w_review_pass_factory
) -> None:
    """review 子命令端到端：Lead → Reviewer → executor → Candidate。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    item = _seed_lead_for_review(db_session)
    ir = db_session.scalars(select(IntelligenceRequirement)).one()
    judgment = w_review_pass_factory(matched_requirement_id=ir.id)
    fake_llm = make_fake_llm_review(judgment)
    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.review.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.review.make_session_factory", lambda engine: fake_factory)
    monkeypatch.setattr("iih.cli.review.make_llm_client", lambda settings: fake_llm)

    rc = main(["review"])

    assert rc == 0
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.CANDIDATE


def test_cli_review_e2e_reject_transitions_to_noise(
    db_session, monkeypatch, w_review_reject_irrelevant
) -> None:
    """review 子命令端到端：Lead → Reviewer → executor → Noise（否决附理由）。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    item = _seed_lead_for_review(db_session)
    fake_llm = make_fake_llm_review(w_review_reject_irrelevant)
    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.review.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.review.make_session_factory", lambda engine: fake_factory)
    monkeypatch.setattr("iih.cli.review.make_llm_client", lambda settings: fake_llm)

    rc = main(["review"])

    assert rc == 0
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.NOISE


def test_cli_review_e2e_no_leads_skips(db_session, monkeypatch) -> None:
    """无 Lead 态条目时 review 命令优雅退出。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.review.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.review.make_session_factory", lambda engine: fake_factory)
    monkeypatch.setattr("iih.cli.review.make_llm_client", lambda settings: None)  # 无 Lead 不触 LLM

    rc = main(["review"])

    assert rc == 0


# ---- IIH-01.03 核实评级 CLI ----


def _seed_candidate_for_verify(db_session, *, credit: str | None = "B") -> IntelligenceItem:
    """预置一条 Candidate 态条目 + 单节点转引链，source.credit 可控。"""
    medium = db_session.scalars(select(Medium).where(Medium.code == "internet")).one()
    modality = db_session.scalars(select(Modality).where(Modality.code == "webpage")).one()
    source = Source(name="W 公司", type=SourceType.COMPANY, confirmed=True, credit=credit)
    item = IntelligenceItem(
        statement="W 公司公告：与 Z 集团签署合资协议",
        status=ItemStatus.CANDIDATE,
        mode=ItemMode.AUTOMATED,
        medium=medium,
        modality=modality,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
        original_snapshot="正文",
        source=source,
    )
    node = ProvenanceChainNode(
        item=item,
        source=source,
        modality=modality,
        medium=medium,
        collected_at=datetime(2026, 9, 14, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([source, item, node])
    db_session.flush()
    return item


def test_cli_verify_e2e_verified_transitions_to_verified(db_session, monkeypatch) -> None:
    """verify 子命令端到端：Candidate + credit=B → Verifier → executor → Verified + rating=B2。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    item = _seed_candidate_for_verify(db_session, credit="B")
    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.verify.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.verify.make_session_factory", lambda engine: fake_factory)

    rc = main(["verify"])

    assert rc == 0
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.VERIFIED
    assert refreshed.rating == "B2"

    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 1
    assert records[0].outcome is VerificationOutcome.VERIFIED
    assert records[0].rating == "B2"


def test_cli_verify_e2e_undetermined_transitions_to_undetermined(db_session, monkeypatch) -> None:
    """verify 子命令端到端：Candidate + credit=None → Verifier → executor → Undetermined。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    item = _seed_candidate_for_verify(db_session, credit=None)
    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.verify.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.verify.make_session_factory", lambda engine: fake_factory)

    rc = main(["verify"])

    assert rc == 0
    refreshed = db_session.get(IntelligenceItem, item.id)
    assert refreshed is not None
    assert refreshed.status is ItemStatus.UNDETERMINED
    assert refreshed.rating is None

    records = db_session.scalars(
        select(VerificationRecord).where(VerificationRecord.item_id == item.id)
    ).all()
    assert len(records) == 1
    assert records[0].outcome is VerificationOutcome.UNDETERMINED
    assert records[0].rating is None


def test_cli_verify_e2e_no_candidates_skips(db_session, monkeypatch) -> None:
    """无 Candidate 态条目时 verify 命令优雅退出。"""
    from contextlib import contextmanager
    from types import SimpleNamespace

    fake_engine = SimpleNamespace(dispose=lambda: None)

    @contextmanager
    def fake_factory():
        yield db_session

    monkeypatch.setattr("iih.cli.verify.make_engine", lambda settings: fake_engine)
    monkeypatch.setattr("iih.cli.verify.make_session_factory", lambda engine: fake_factory)

    rc = main(["verify"])

    assert rc == 0
