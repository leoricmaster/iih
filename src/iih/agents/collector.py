"""采集智能体 Collector（doc-06 §3）· 最简归因版：人工提交路径 + 自动拉取路径。

人工提交不经定向任务化：文字纪要与附件转写稿（IIH-02.01 录音）共用 LLM 抽取陈述
+ 归因信源与途径（溯源五要素），每条陈述一个「情报条目新建」提案；
落账由状态机执行器执行（本智能体不直接写账）。附件路径原文快照走第三轨
（挂素材 + 派生级，doc-04 §1）。

自动拉取（IIH-01.15 两跳）：入口页选链 → 抓文章页 → 文章页抽陈述；
原文 URL 即实际抓取的文章页地址（确定性），原文快照为原始 HTML 存对象存储。

池外自由探索（IIH-05.02）：自动拉取末尾按 IR.explore_ratio 概率探索池外候选链接
→ 发现新信源产出 SourceDiscoveryProposal 进待确认队列（decision-05 通道二）。
"""

import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from instructor import Instructor
from openai.types.completion import CompletionUsage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.agents.director import CollectionTask
from iih.config import get_settings
from iih.ledger.models import (
    Derivation,
    IntelligenceItem,
    ItemMode,
    LlmCall,
    Material,
    Medium,
    Outlet,
    ProvenanceChainNode,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceItemNewPayload,
    IntelligenceItemNewProposal,
    ItemProvenanceAppendPayload,
    ItemProvenanceAppendProposal,
    ProvenanceData,
    SourceDiscoveryPayload,
    SourceDiscoveryProposal,
)
from iih.ledger.state_machine import StateMachineExecutor
from iih.tools import search as search_module
from iih.tools.asr import split_speakers
from iih.tools.html_normalize import extract_link_candidates, fingerprint, normalize
from iih.tools.search import SearchError
from iih.tools.snapshot_store import SnapshotStore

if TYPE_CHECKING:
    from iih.pipeline import RoundSummary

ATTRIBUTION_SYSTEM_PROMPT = """你是情报采集智能体的归因模块。
给定一条情报陈述与其获取媒介，推断信源与发布途径。

要求：
- source_name：发布主体（谁在说），从陈述中的公司 / 机构 / 人物推断；
- source_type：主体类型；
- outlet_name：该场景下的具体发布出口（如「渠道大会现场」），无法推断则留空；
- rationale：一句话归因依据，将记入提案的「依据」。"""


class AttributionResult(BaseModel):
    """LLM 结构化归因输出（instructor 按此 schema 校验）。"""

    source_name: str = Field(description="发布主体名，如「W 公司」")
    source_type: SourceType = Field(
        description="主体类型：company/government/organization/media/person/other"
    )
    outlet_name: str | None = Field(
        default=None, description="发布出口，如「渠道大会现场」；无法推断留空"
    )
    rationale: str = Field(description="一句话归因依据")


ARTICLE_SELECTION_SYSTEM_PROMPT = """你是情报采集智能体的选链模块。
给定途径入口页（多为列表页 / 首页）的正文文本与候选链接清单（链接 + 锚文本），
判断入口页本身是否已是文章正文页；若不是，选出一条最值得作为本次采集对象的文章页链接。

要求：
- url：入口页即文章正文页时返回空字符串；否则从候选清单中选一条与页面主题最相关的
  文章 / 详情页链接（原文照抄清单中的链接，不得自造）；
- rationale：一句话选链依据。"""


class ArticleSelectionResult(BaseModel):
    """LLM 结构化选链输出。"""

    url: str = Field(default="", description="选中的文章页链接；入口页即文章页时为空字符串")
    rationale: str = Field(description="一句话选链依据")


EXTRACTION_SYSTEM_PROMPT = """你是情报采集智能体的陈述抽取模块。
给定文章页的正文文本与其来源（信源·途径），识别其中**最具情报价值的一条**陈述。

要求：
- statement：客观陈述句，描述事实而非评价；若页面无情报价值内容，返回空字符串；
- event_time：陈述所述事实的发生日期（ISO 格式，如 2026-08-30），正文无明确日期
  依据则留空，不得编造；
- rationale：一句话说明为何选此陈述（依据记入提案）。"""


class StatementExtractionResult(BaseModel):
    """LLM 结构化陈述抽取输出。"""

    statement: str = Field(description="页面中最具情报价值的一条陈述；无则空字符串")
    event_time: datetime | None = Field(
        default=None, description="陈述所述事实的发生日期；正文无明确日期依据则留空"
    )
    rationale: str = Field(description="一句话抽取依据")


EXPLORATION_KEYWORD_SYSTEM_PROMPT = """你是情报采集智能体的池外探索关键词提取模块。
给定情报需求的内容规格（自由文本），提取 2–4 个用于互联网检索的关键词，
倾向具体实体（公司 / 产品 / 人物）与事件主题，避免泛化词。

要求：
- keywords：关键词列表（2–4 个）；内容规格无可用信息返回空列表；
- rationale：一句话提取依据。
"""


class ExplorationKeywordResult(BaseModel):
    """LLM 结构化关键词提取输出。"""

    keywords: list[str] = Field(default_factory=list, description="检索关键词列表")
    rationale: str = Field(description="一句话提取依据")


EXPLORATION_RESULT_SELECTION_SYSTEM_PROMPT = """你是情报采集智能体的池外探索选链模块。

给定互联网检索结果清单（URL + 标题 + 内容片段，已排除本途径所属域），选一条
「最可能属于尚未登记信源」的结果——倾向明确发布主体的文章 / 报道页，
避免目录 / 栏目 / 导航页。

要求：
- url：原样照抄清单中的 URL，不得自造；清单为空返回空字符串；
- rationale：一句话选链依据（为何此结果值得探索）。
"""


class ExplorationResultSelectionResult(BaseModel):
    """LLM 结构化检索结果选链输出。"""

    url: str = Field(default="", description="选中的探索目标 URL；清单为空时为空字符串")
    rationale: str = Field(description="一句话选链依据")


EXPLORATION_ATTRIBUTION_SYSTEM_PROMPT = """你是情报采集智能体的池外探索归因模块。
给定一条从互联网检索发现的目标页正文，推断该页所属发布主体。

要求：
- source_name：发布主体名；文本无明确主体信息则返回空字符串；
- source_type：主体类型；
- rationale：一句话归因依据。
"""


class ExplorationAttributionResult(BaseModel):
    """LLM 结构化池外探索归因输出。"""

    source_name: str = Field(description="发布主体名；无明确主体则空字符串")
    source_type: SourceType = Field(
        description="主体类型：company/government/organization/media/person/other"
    )
    rationale: str = Field(description="一句话归因依据")


MANUAL_EXTRACTION_SYSTEM_PROMPT = """你是情报采集智能体的陈述抽取模块。
给定一段人工录入的素材文本（会议 / 访谈纪要、当场记录的要点）与其媒介，
识别其中**有情报价值的客观事实陈述**。

情报价值四标准——陈述须同时满足：
1. 客观：描述已发生或可验证的事实，不含主观判断、预测、评价；
2. 原子：一条陈述只含一个可独立判定的事实，合并句须拆到原子；
3. 可溯源：能归因到发表主体（谁在说），非无主泛述；
4. 可核实：含可被第三方证据证伪的具体内容（实体 / 数据 / 时间 / 动作）。

可抽类型——下列事实可抽：
- 已发生的具体事件（发布、合作、投产、人事变动等动作）；
- 已公开宣布的计划或决策（下一步行动）；
- 引用的第三方数据或具体指标（份额、产能、销量、价格等）；
- 实体属性与关系（机构 / 人物 / 产品的客观属性与关联）。

必舍清单——下列内容一律不抽：
- 主观判断 / 评价 / 预测（"前景广阔"、"预计将增长"、"被认为优秀"）；
- 引述他人观点（"张三认为……"）——观点本身非客观事实；
- 现场描写、气氛、寒暄、议程流程、主持人介绍；
- 未形成结论的讨论、开放性提问、假设性表述；
- 无主泛述（"业内普遍认为"、"有消息称"无可核验来源）；
- 合并总结句（"会议讨论了 A、B、C"——若 A、B、C 各自含事实则各自成条，否则舍）。

要求：
- statements：按上述标准抽取的客观事实陈述列表；同义合并、按原文顺序；
  多人发言的素材按发言人逐要点拆分，但只抽发言中符合上述标准的事实性内容；
  超过 10 条时只取情报价值最高的 10 条；无符合标准的内容返回空列表；
- 每条 event_time：该事实的发生日期（ISO 格式，如 2026-08-30），文本无明确日期依据则留空，不得编造；
- 每条 rationale：一句话说明该陈述符合可抽类型的关键点（如"已发生的具体动作"或"引用的具体数据"）。
"""


class ManualStatement(BaseModel):
    """纪要抽取出的单条陈述。"""

    statement: str = Field(description="客观陈述句")
    event_time: datetime | None = Field(
        default=None, description="该事实的发生日期；文本无明确日期依据则留空"
    )
    rationale: str = Field(description="一句话抽取依据")


class ManualExtractionResult(BaseModel):
    """LLM 结构化纪要抽取输出（一次提交 → 多条陈述）。"""

    statements: list[ManualStatement] = Field(default_factory=list, description="抽取的陈述列表")


def _as_utc(value: datetime | None) -> datetime | None:
    """LLM 输出的 naive 时间按 UTC 入账（库内时间戳一律 aware UTC）。"""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class Collector:
    """采集智能体执行器（判断层）：无状态、输出提案。"""

    AGENT_NAME = "collector"

    def __init__(self, llm: Instructor, session: Session, model: str) -> None:
        self.llm = llm
        self.session = session
        self.model = model

    def submit_manual(
        self, *, medium_code: str, statement: str
    ) -> list[IntelligenceItemNewProposal]:
        """人工提交路径：文字纪要 → LLM 抽取陈述 + 最简归因 → 每条陈述一个线索提案（doc-07 §2.3）。

        抽取为空（无情报价值）不调归因，返回空列表。
        """
        medium = self.session.scalars(select(Medium).where(Medium.code == medium_code)).first()
        if medium is None:
            raise ValueError(f"媒介不存在：{medium_code}")

        statements = self._extract_statements(medium=medium, text=statement)
        if not statements:
            return []
        attribution = self._attribute(medium=medium, text=statement)

        collected_at = datetime.now(UTC)
        return [
            IntelligenceItemNewProposal(
                payload=IntelligenceItemNewPayload(
                    statement=s.statement.strip(),
                    mode=ItemMode.MANUAL,
                    event_time=_as_utc(s.event_time),
                    content_fingerprint=fingerprint(s.statement.strip()),
                ),
                provenance=ProvenanceData(
                    modality_code="text",
                    medium_code=medium.code,
                    collected_at=collected_at,
                    original_snapshot=statement,  # 文字载体：原文快照 = 提交文本
                    source_name=attribution.source_name,
                    source_type=attribution.source_type,
                    outlet_name=attribution.outlet_name or None,
                ),
                rationale=f"{s.rationale}（归因：{attribution.rationale}）",
            )
            for s in statements
        ]

    def submit_material(
        self, *, material: Material, derivation: Derivation
    ) -> list[IntelligenceItemNewProposal]:
        """附件路径（IIH-02.01 录音）：转写稿逐发言人切段，每段抽取陈述 + 归因 → 线索提案。

        发言人已人工标记实名则逐人各自成源；未标记保留「发言人N」原名，经待确认
        信源闭环（decision-05）确认时改名并入。无发言人前缀回退整稿单归因。
        原文快照走第三轨（挂素材 + 派生级，doc-04 §1），条目不内嵌转写稿；
        采集时间取素材采集时间，载体取素材载体。
        """
        transcript = derivation.output_text or ""
        proposals: list[IntelligenceItemNewProposal] = []
        for _speaker, segment in split_speakers(transcript):
            statements = self._extract_statements(medium=material.medium, text=segment)
            if not statements:
                continue
            attribution = self._attribute(medium=material.medium, text=segment)
            proposals.extend(
                IntelligenceItemNewProposal(
                    payload=IntelligenceItemNewPayload(
                        statement=s.statement.strip(),
                        mode=ItemMode.MANUAL,
                        event_time=_as_utc(s.event_time),
                        content_fingerprint=fingerprint(s.statement.strip()),
                        material_id=material.id,
                        derivation_id=derivation.id,
                    ),
                    provenance=ProvenanceData(
                        modality_code=material.modality.code,
                        medium_code=material.medium.code,
                        collected_at=material.collected_at,
                        source_name=attribution.source_name,
                        source_type=attribution.source_type,
                        outlet_name=attribution.outlet_name or None,
                    ),
                    rationale=f"{s.rationale}（归因：{attribution.rationale}）",
                )
                for s in statements
            )
        return proposals

    def _extract_statements(self, *, medium: Medium, text: str) -> list[ManualStatement]:
        """纪要抽取（文字纪要与附件转写稿共用）：空结果不计量归因、直接返回。"""
        extraction, completion = self.llm.chat.completions.create_with_completion(
            response_model=ManualExtractionResult,
            messages=[
                {"role": "system", "content": MANUAL_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"媒介：{medium.name}\n素材文本：\n{text}"},
            ],
            model=self.model,
            temperature=0,  # 抽取需可复现：同输入应同输出
        )
        self._meter(target="manual_submission", usage=completion.usage)
        return [s for s in extraction.statements if s.statement.strip()][:20]

    def _attribute(self, *, medium: Medium, text: str) -> AttributionResult:
        """最简归因：整份素材文本一次归因（doc-06 §3）。"""
        attribution, completion = self.llm.chat.completions.create_with_completion(
            response_model=AttributionResult,
            messages=[
                {"role": "system", "content": ATTRIBUTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"媒介：{medium.name}\n陈述：{text}"},
            ],
            model=self.model,
        )
        self._meter(target="manual_submission", usage=completion.usage)
        return attribution

    def collect_outlet(
        self,
        *,
        task: CollectionTask,
        html: str,
        fetch_article: Callable[[str], str],
        store: SnapshotStore | None = None,
        summary: "RoundSummary | None" = None,
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """自动拉取路径（doc-06 §3 两跳 + 前置过滤 + IIH-05.02 池外自由探索·检索式）。

        主任务（两跳采集）产出主 proposal 由调用方落账；
        池外探索为副产品——按 task.explore_ratio 概率触发，按 IR.content_spec 经
        Tavily 检索产出 SourceDiscoveryProposal 直接落账（同 session），
        失败/驳回静默跳过不影响主任务。
        """
        proposal = self._collect_outlet_main(
            task=task, html=html, fetch_article=fetch_article, store=store
        )
        if task.explore_ratio > 0 and random.random() < task.explore_ratio:
            self._explore_outside_pool(task=task, fetch_article=fetch_article, summary=summary)
        return proposal

    def _collect_outlet_main(
        self,
        *,
        task: CollectionTask,
        html: str,
        fetch_article: Callable[[str], str],
        store: SnapshotStore | None,
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """自动拉取主任务（doc-06 §3 两跳 + 前置过滤）。

        流程：
        1. 选链（LLM）：入口页多为列表/首页——判本页是否即文章页，否则选一条文章链接
        2. 单跳回退：入口页即文章页，直接以本页为文章页
        3. URL 级去重（确定性）：选链命中已采 URL → 追加节点提案，不抓取不抽取
        4. 抓文章页（fetch_article）→ 归一化文本 + 内容指纹
        5. 指纹命中：追加节点提案（不调抽取 LLM）
        6. 抽取陈述（LLM）：空 → None（计量已发生）；非空 → 新建提案
           （原文 URL = 文章页地址；原始 HTML 经 store 存对象存储，键入提案）
        """
        entry_text = normalize(html)
        candidates = extract_link_candidates(html, base_url=task.url)
        block = (
            "\n".join(f"- {url} ｜ {text or '（无锚文本）'}" for url, text in candidates)
            if candidates
            else "（无）"
        )
        selection, completion = self.llm.chat.completions.create_with_completion(
            response_model=ArticleSelectionResult,
            messages=[
                {"role": "system", "content": ARTICLE_SELECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"信源：{task.source_name}\n途径：{task.outlet_name}"
                        f"\n入口页正文：\n{entry_text}\n\n候选链接清单：\n{block}"
                    ),
                },
            ],
            model=self.model,
            temperature=0,  # 选链需可复现：试采与正式运行同输入应同输出
        )
        self._meter(target="outlet_link_select", usage=completion.usage)

        article_url = selection.url.strip()
        if not article_url or article_url == task.url:
            return self._collect_article(
                task=task, url=task.url, html=html, text=entry_text, store=store
            )

        existing = self.session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.original_url == article_url)
        ).first()
        if existing is not None:
            return self._append_or_none(
                existing_id=existing.id, task=task, original_url=article_url
            )

        article_html = fetch_article(article_url)
        return self._collect_article(
            task=task,
            url=article_url,
            html=article_html,
            text=normalize(article_html),
            store=store,
        )

    def _explore_outside_pool(
        self,
        *,
        task: CollectionTask,
        fetch_article: Callable[[str], str],
        summary: "RoundSummary | None",
    ) -> None:
        """池外自由探索（doc-06 §3、decision-05 通道二、IIH-05.02 检索式）。

        IR.content_spec → LLM 提取关键词 → Tavily 检索 top-5 → LLM 选链（排除本途径域）
        → fetch → 归一化 → LLM 归因 → 信源名不在信源库（含别名）则产出
        SourceDiscoveryProposal 直接落账；关键词空/检索失败/无候选/撞名/无主体/
        抓取失败/LLM 失败/驳回一律静默跳过，不阻断主任务。
        """
        if not task.content_spec.strip():
            return

        keywords, completion = self.llm.chat.completions.create_with_completion(
            response_model=ExplorationKeywordResult,
            messages=[
                {"role": "system", "content": EXPLORATION_KEYWORD_SYSTEM_PROMPT},
                {"role": "user", "content": f"内容规格：\n{task.content_spec}"},
            ],
            model=self.model,
            temperature=0,  # 关键词提取需可复现
        )
        self._meter(target="outlet_exploration", usage=completion.usage)

        if not keywords.keywords:
            return

        query = " ".join(keywords.keywords)
        try:
            results = search_module.search(
                query, api_key=get_settings().tavily_api_key, max_results=5
            )
        except SearchError:
            return  # 检索失败静默跳过

        own_domain = urlparse(task.url).netloc
        outside = [r for r in results if urlparse(r.url).netloc != own_domain]
        if not outside:
            return

        block = "\n".join(
            f"- {r.url} ｜ {r.title or '（无标题）'} ｜ {r.content[:80]}" for r in outside
        )
        selection, completion = self.llm.chat.completions.create_with_completion(
            response_model=ExplorationResultSelectionResult,
            messages=[
                {"role": "system", "content": EXPLORATION_RESULT_SELECTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"检索结果清单：\n{block}"},
            ],
            model=self.model,
            temperature=0,  # 选链需可复现
        )
        self._meter(target="outlet_exploration", usage=completion.usage)

        target_url = selection.url.strip()
        if not target_url:
            return

        try:
            target_html = fetch_article(target_url)
        except Exception:  # noqa: BLE001 - 探索失败静默跳过
            return

        target_text = normalize(target_html)
        attribution, completion = self.llm.chat.completions.create_with_completion(
            response_model=ExplorationAttributionResult,
            messages=[
                {"role": "system", "content": EXPLORATION_ATTRIBUTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"探索目标正文：\n{target_text}"},
            ],
            model=self.model,
        )
        self._meter(target="outlet_exploration", usage=completion.usage)

        source_name = attribution.source_name.strip()
        if not source_name:
            return  # 探索目标无明确主体信息

        existing = self.session.scalars(select(Source).where(Source.name == source_name)).first()
        if existing is None:
            from iih.ledger.models import SourceAlias

            alias = self.session.scalars(
                select(SourceAlias).where(SourceAlias.name == source_name)
            ).first()
            existing = alias.source if alias is not None else None
        if existing is not None:
            return  # 信源已登记（含别名），不重复建

        proposal = SourceDiscoveryProposal(
            payload=SourceDiscoveryPayload(
                source_name=source_name,
                source_type=attribution.source_type,
            ),
            rationale=(
                f"池外自由探索：按「{query}」检索发现 {source_name}"
                f"（发现来源 URL：{target_url}；关键词依据：{keywords.rationale}；"
                f"选链依据：{selection.rationale}；归因依据：{attribution.rationale}）"
            ),
        )
        try:
            StateMachineExecutor().execute(proposal, session=self.session)
        except Exception:  # noqa: BLE001 - 驳回（撞名等）静默跳过
            return
        if summary is not None:
            summary.discovered_sources += 1

    def _collect_article(
        self,
        *,
        task: CollectionTask,
        url: str,
        html: str,
        text: str,
        store: SnapshotStore | None,
    ) -> IntelligenceItemNewProposal | ItemProvenanceAppendProposal | None:
        """文章页采集：指纹去重 → 抽取陈述 → 新建提案（原文 URL = 本页地址）。"""
        fp = fingerprint(text)
        existing = self.session.scalars(
            select(IntelligenceItem).where(IntelligenceItem.content_fingerprint == fp)
        ).first()
        if existing is not None:
            return self._append_or_none(existing_id=existing.id, task=task, original_url=url)

        user_content = f"信源：{task.source_name}\n途径：{task.outlet_name}\n正文：\n{text}"
        extraction, completion = self.llm.chat.completions.create_with_completion(
            response_model=StatementExtractionResult,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=self.model,
            temperature=0,  # 抽取需可复现：同输入应同输出
        )
        self._meter(target="outlet_collection", usage=completion.usage)

        if not extraction.statement.strip():
            return None  # LLM 判定无情报价值内容

        return IntelligenceItemNewProposal(
            payload=IntelligenceItemNewPayload(
                statement=extraction.statement.strip(),
                mode=ItemMode.AUTOMATED,
                event_time=_as_utc(extraction.event_time),
                content_fingerprint=fp,
                original_url=url,
                snapshot_object_key=store.put_html(html) if store is not None else None,
            ),
            provenance=ProvenanceData(
                modality_code="webpage",
                medium_code="internet",
                collected_at=datetime.now(UTC),
                source_name=task.source_name,
                source_type=task.source_type,
                outlet_name=task.outlet_name,
            ),
            rationale=extraction.rationale,
        )

    def _append_or_none(
        self, *, existing_id: int, task: CollectionTask, original_url: str
    ) -> ItemProvenanceAppendProposal | None:
        """命中既有条目时追加转引链节点；节点已存在（本轮无新内容）返回 None。"""
        source = self.session.scalars(select(Source).where(Source.name == task.source_name)).first()
        outlet = (
            self.session.scalars(
                select(Outlet).where(Outlet.source_id == source.id, Outlet.name == task.outlet_name)
            ).first()
            if source is not None and task.outlet_name
            else None
        )
        if source is not None and (not task.outlet_name or outlet is not None):
            linked = self.session.scalars(
                select(ProvenanceChainNode).where(
                    ProvenanceChainNode.item_id == existing_id,
                    ProvenanceChainNode.source_id == source.id,
                    ProvenanceChainNode.outlet_id == (outlet.id if outlet else None),
                )
            ).first()
            if linked is not None:
                return None
        return ItemProvenanceAppendProposal(
            payload=ItemProvenanceAppendPayload(
                item_id=existing_id,
                source_name=task.source_name,
                source_type=task.source_type,
                outlet_name=task.outlet_name,
                original_url=original_url,
                collected_at=datetime.now(UTC),
            ),
            rationale=f"已采集内容命中既有条目 #{existing_id}，追加转引链节点",
        )

    def _meter(self, *, target: str, usage: CompletionUsage) -> None:
        """调用计量即时入账：LLM 成本在调用时已发生，与提案成败无关（技术架构 §1）。"""
        self.session.add(
            LlmCall(
                agent=self.AGENT_NAME,
                target=target,
                model=self.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        )
        self.session.commit()
