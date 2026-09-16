"""提案契约（技术架构 §5）：智能体对记账层的写入一律为提案——类型/产出/依据/溯源/公式版本。"""

from datetime import date, datetime
from typing import ClassVar

from pydantic import BaseModel

from iih.ledger.models import (
    ItemMode,
    RejectionReasonEnum,
    ReviewDecisionEnum,
    SourceType,
    VerificationOutcome,
)


class ProvenanceData(BaseModel):
    """溯源五要素（doc-05 §5）：载体+媒介+采集时间+原文快照+信源/途径归因。

    完备性由状态机执行器校验（无溯源不落账）。
    原文快照三轨（doc-04 §1）：人工提交 = 提交文本（original_snapshot）；自动拉取 =
    原始网页 HTML 对象（snapshot_object_key，入 payload）；附件路径 = 挂素材 +
    所自派生级（material_id/derivation_id，入 payload），条目不内嵌快照。
    """

    modality_code: str  # 载体
    medium_code: str  # 媒介
    collected_at: datetime  # 采集时间
    original_snapshot: str | None = None  # 原文快照：人工提交文本
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
    snapshot_object_key: str | None = None  # 原文快照对象键（原始网页 HTML）
    # 附件路径专用（doc-04 §1 第三轨）：挂素材 + 所自派生级
    material_id: int | None = None
    derivation_id: int | None = None


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
    initial_credit: str | None = None  # 初始信用档（人工评估 · 冷启动设档；空 = 不设档）


class SourceRegisterProposal(Proposal):
    """提案类型「种子信源登记」：双通道确认制通道一 · 人工登记（decision-05）。

    信源登记非情报产出，溯源五要素不适用——本提案无 provenance、无 formula_version。
    校验由状态机执行器执行：字段完整 + medium=internet + 信源名唯一 + 同主体途径名唯一。
    """

    PROPOSAL_TYPE = "source_register"

    payload: SourceRegisterPayload


class SourceConfirmPayload(BaseModel):
    """「待确认信源确认」产出：目标信源 ID + 初始信用档 + 修正名/类型（可空，IIH-05.01）。"""

    source_id: int
    initial_credit: str
    name: str | None = None  # 修正信源名；撞既有已确认信源名即合并迁移，旧名留档为别名
    source_type: SourceType | None = None  # 修正类型；空 = 沿用提取结果，并入路径忽略


class SourceConfirmProposal(Proposal):
    """提案类型「待确认信源确认」：待确认 → 已确认，入信源库（decision-05 准入把关）。

    消费方确认非情报产出，无 provenance、无 formula_version（同 source_register）。
    确认必设初始信用档（doc-04 §2.3 解死锁）；拒绝留痕（rejected_at）随确认清空；
    携带修正名时改名入池（旧名留档为别名，归因解析按别名归到本信源），
    撞既有已确认信源名则并入该信源（条目/转引链/途径迁移）。
    """

    PROPOSAL_TYPE = "source_confirm"

    payload: SourceConfirmPayload


class SourceRejectPayload(BaseModel):
    """「待确认信源拒绝」产出：目标信源 ID（IIH-05.01）。"""

    source_id: int


class SourceRejectProposal(Proposal):
    """提案类型「待确认信源拒绝」：不入池、留痕（rejected_at），confirmed 保持 False。

    已归因到该信源的既有条目不受影响；拒绝非终态——再次归因命中同名信源仍可确认。
    """

    PROPOSAL_TYPE = "source_reject"

    payload: SourceRejectPayload


class SourceDiscoveryPayload(BaseModel):
    """「新信源发现」产出：信源主体字段（decision-05 通道二，IIH-05.02）。

    发现来源 URL 与依据记入提案 rationale，payload 仅含信源主体。
    """

    source_name: str
    source_type: SourceType


class SourceDiscoveryProposal(Proposal):
    """提案类型「新信源发现」：池外自由探索发现的新信源（doc-06 §3、decision-05 通道二）。

    非情报产出，无 formula_version；落账 Source(confirmed=False) 进待确认队列，
    与人工归因产生的待确认信源同通路确认（IIH-05.01 确认入口）。
    """

    PROPOSAL_TYPE = "source_discovery"

    payload: SourceDiscoveryPayload


# ---- IIH-01.08 互联网信源自动拉取 ----


class IntelligenceRequirementRegisterPayload(BaseModel):
    """「情报需求登记」产出：name + content_spec + 需求级采集配置（IIH-03.01/05.02）。"""

    name: str
    content_spec: str  # 主题、关键词、信源偏好、时效要求等自由文本
    collection_frequency: str | None = None  # "1h"/"24h"；空=继承全局间隔
    event_freshness: str | None = None  # "7d"/"24h"；空=不限
    valid_from: date | None = None  # 生效窗口起；空=常驻
    valid_until: date | None = None  # 生效窗口止；空=常驻
    source_ids: list[int] = []  # 信源绑定；空=全部已确认信源
    explore_ratio: float | None = None  # 池外自由探索触发概率 0–1；None=0（IIH-05.02）


class IntelligenceRequirementRegisterProposal(Proposal):
    """提案类型「情报需求登记」：迁移 [*] → 草稿 Draft（doc-02 §4.1）。

    消费方登记非情报产出，无 provenance、无 formula_version。
    需求级采集配置（IIH-03.01）：频率/事件时效/生效窗口/信源绑定，校验合法性后落账。
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


class IntelligenceRequirementPausePayload(BaseModel):
    """「情报需求暂停」产出：目标需求 ID。"""

    requirement_id: int


class IntelligenceRequirementPauseProposal(Proposal):
    """提案类型「情报需求暂停」：激活 Active → 暂停 Paused（doc-02 §4.1）。"""

    PROPOSAL_TYPE = "intelligence_requirement_pause"

    payload: IntelligenceRequirementPausePayload


class IntelligenceRequirementResumePayload(BaseModel):
    """「情报需求恢复」产出：目标需求 ID。"""

    requirement_id: int


class IntelligenceRequirementResumeProposal(Proposal):
    """提案类型「情报需求恢复」：暂停 Paused → 激活 Active（doc-02 §4.1）。"""

    PROPOSAL_TYPE = "intelligence_requirement_resume"

    payload: IntelligenceRequirementResumePayload


class IntelligenceRequirementClosePayload(BaseModel):
    """「情报需求关闭」产出：目标需求 ID。"""

    requirement_id: int


class IntelligenceRequirementCloseProposal(Proposal):
    """提案类型「情报需求关闭」：激活/暂停 → 关闭 Closed（终态，doc-02 §4.1）。"""

    PROPOSAL_TYPE = "intelligence_requirement_close"

    payload: IntelligenceRequirementClosePayload


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


class ItemReviewDisputePayload(BaseModel):
    """「审查异议重审」产出：item_id + 重审决策（同 ReviewPayload 决策字段）。"""

    item_id: int
    decision: ReviewDecisionEnum
    reason_type: RejectionReasonEnum | None = None  # 维持否决时必填
    matched_requirement_id: int | None = None  # 重审通过时必填


class ItemReviewDisputeProposal(Proposal):
    """提案类型「审查异议重审」：Noise → Candidate（重审通过）或维持 Noise（doc-02 §4.3、§6）。

    由消费方审查异议触发、审查智能体携异议理由重审后产出；重审决策落 ReviewDecision
    （版本化历史），依据记入 rationale。
    """

    PROPOSAL_TYPE = "intelligence_item_review_dispute"

    payload: ItemReviewDisputePayload


# ---- IIH-01.03 核实评级 ----


class VerificationPayload(BaseModel):
    """「核实评级」产出：item_id + outcome + N/R/credibility/rating。

    VERIFIED：N ≥ 1 + R（A–F）+ credibility（1–6）+ rating（如 "B2"）必填。
    UNDETERMINED：R/credibility/rating 为空（N 仍记，已穿透统计）；公式版本为空。
    """

    item_id: int
    outcome: VerificationOutcome
    independent_source_count: int  # N：穿透转引链后的独立信源数
    source_reliability: str | None = None  # R：A–F；VERIFIED 必填
    content_credibility: int | None = None  # 1–6；VERIFIED 必填
    rating: str | None = None  # 如 "B2"；VERIFIED 必填


class VerificationProposal(Proposal):
    """提案类型「核实评级」：Candidate → Verified 或 Undetermined（doc-02 §4.3、doc-06 §5）。

    核实评级含公式判定，formula_version 记入提案顶层（继承自 Proposal.formula_version）；
    无独立 provenance 字段（核实非采集动作，溯源五要素已在条目新建时落账）。
    依据 + 公式版本 + 变量快照（N/R/credibility/rating）落账到 VerificationRecord 表，
    满足 doc-08 #8 与 doc-04 §1 推理记录字段定义。
    """

    PROPOSAL_TYPE = "intelligence_item_verification"

    payload: VerificationPayload


# ---- IIH-01.13 存疑重核回流 ----


class ItemReverifyPayload(BaseModel):
    """「存疑重核」产出：item_id。"""

    item_id: int


class ItemReverifyProposal(Proposal):
    """提案类型「存疑重核」：Undetermined → Candidate（doc-02 §4.1「复核期到 / 新证据」回流）。

    典型新证据：信源画像补设信用档（R 由空变有）。回到候选后由核实段重评；
    无独立 provenance（非采集动作）；依据（新证据说明）记入 rationale。
    """

    PROPOSAL_TYPE = "intelligence_item_reverify"

    payload: ItemReverifyPayload
