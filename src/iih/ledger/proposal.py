"""提案契约（技术架构 §5）：智能体对记账层的写入一律为提案——类型/产出/依据/溯源/公式版本。"""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel

from iih.ledger.models import ItemMode, RejectionReasonEnum, ReviewDecisionEnum, SourceType


class ProvenanceData(BaseModel):
    """溯源五要素（doc-05 §5）：载体+媒介+采集时间+原文快照+信源/途径归因。

    完备性由状态机执行器校验（无溯源不落账）。
    """

    modality_code: str  # 载体
    medium_code: str  # 媒介
    collected_at: datetime  # 采集时间
    original_snapshot: str  # 原文快照 / 链接
    source_name: str  # 信源归因：发布主体
    source_type: SourceType
    outlet_name: str | None = None  # 途径归因：发布出口（线下场景）


class IntelligenceItemNewPayload(BaseModel):
    """「情报条目新建」产出：目标实体字段值（溯源五要素之外的部分）。"""

    statement: str  # 陈述内容
    mode: ItemMode
    event_time: datetime | None = None  # 事件时间
    # 自动拉取路径专用（doc-06 §3 前置过滤）；人工提交路径不设
    content_fingerprint: str | None = None
    original_url: str | None = None


class Proposal(BaseModel):
    """提案契约基类。"""

    PROPOSAL_TYPE: ClassVar[str]

    rationale: str  # 依据：判断的证据引用与推理过程
    formula_version: str | None = None  # 公式版本：涉及公式判定时记入


class IntelligenceItemNewProposal(Proposal):
    """提案类型「情报条目新建」：迁移 [*] → 线索 Lead（doc-02 §4.3）。"""

    PROPOSAL_TYPE = "intelligence_item_new"

    payload: IntelligenceItemNewPayload
    provenance: ProvenanceData


class SourceRegisterPayload(BaseModel):
    """「种子信源登记」产出：主体字段 + 首条互联网途径字段（doc-07 §2.1、原型信源库页）。"""

    source_name: str  # 主体名称
    source_type: SourceType
    outlet_name: str  # 途径名（如「官网」）
    outlet_entry: str  # 采集入口：网址 / RSS / 账号 ID


class SourceRegisterProposal(Proposal):
    """提案类型「种子信源登记」：双通道确认制通道一 · 人工登记（decision-05）。

    信源登记非情报产出，溯源五要素不适用——本提案无 provenance、无 formula_version。
    校验由状态机执行器执行：字段完整 + medium=internet + 信源名唯一 + 同主体途径名唯一。
    """

    PROPOSAL_TYPE = "source_register"

    payload: SourceRegisterPayload


# ---- IIH-01.08 互联网信源自动拉取 ----


class IntelligenceRequirementRegisterPayload(BaseModel):
    """「情报需求登记」产出：name + content_spec（doc-04 §1）。"""

    name: str
    content_spec: str  # 主题、关键词、信源偏好、时效要求等自由文本


class IntelligenceRequirementRegisterProposal(Proposal):
    """提案类型「情报需求登记」：迁移 [*] → 草稿 Draft（doc-02 §4.1）。

    消费方登记非情报产出，无 provenance、无 formula_version。
    本任务最简：豁免「提出方」（单消费方前提）与「生效窗口」（范围外含调度节奏）。
    """

    PROPOSAL_TYPE = "intelligence_requirement_register"

    payload: IntelligenceRequirementRegisterPayload


class IntelligenceRequirementActivatePayload(BaseModel):
    """「情报需求激活」产出：目标需求 ID。"""

    requirement_id: int


class IntelligenceRequirementActivateProposal(Proposal):
    """提案类型「情报需求激活」：草稿 Draft → 激活 Active（doc-02 §4.1）。"""

    PROPOSAL_TYPE = "intelligence_requirement_activate"

    payload: IntelligenceRequirementActivatePayload


class ItemProvenanceAppendPayload(BaseModel):
    """「转引链节点追加」产出：目标既有条目 + 新信源引用（doc-06 §3 前置过滤命中路径）。"""

    item_id: int
    source_name: str
    source_type: SourceType
    outlet_name: str | None = None
    original_url: str | None = None
    collected_at: datetime


class ItemProvenanceAppendProposal(Proposal):
    """提案类型「转引链节点追加」：指纹命中既有条目时追加信源引用，不新建条目（doc-06 §3）。

    溯源信息内嵌 payload（item_id + 信源/途径 + 采集时间 + URL），无独立 provenance 字段。
    """

    PROPOSAL_TYPE = "item_provenance_append"

    payload: ItemProvenanceAppendPayload


# ---- IIH-01.02 线索审查过滤 ----


class ReviewPayload(BaseModel):
    """「审查决策」产出：item_id + decision + reason_type（否决）+ matched_requirement_id（通过）。

    本里程碑最简：相关性 + 有效性初筛；事件同一性（DUPLICATE）与实体归一暂缓。
    """

    item_id: int
    decision: ReviewDecisionEnum
    reason_type: RejectionReasonEnum | None = None  # REJECT 时必填
    matched_requirement_id: int | None = None  # PASS 时必填


class ReviewProposal(Proposal):
    """提案类型「审查决策」：迁移 Lead → Candidate（PASS）或 Lead → Noise（REJECT）（doc-02 §4.3）。

    审查非情报产出，无 provenance、无 formula_version；依据记入 rationale，
    落账时持久化到 ReviewDecision 表以满足 doc-08 #8「智能体产出附依据，无溯源不落账」。
    """

    PROPOSAL_TYPE = "intelligence_item_review"

    payload: ReviewPayload
