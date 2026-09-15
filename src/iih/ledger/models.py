"""溯源存储 schema：媒介、载体、信源、途径、情报条目（doc-04 §1；English 命名见术语表 §三/§六）。"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iih.db import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


def _sa_enum(enum_cls: type[enum.Enum]) -> Enum:
    """枚举列：VARCHAR 落库、存 value（小写 English 命名）。"""
    return Enum(enum_cls, native_enum=False, values_callable=_enum_values)


class ItemStatus(enum.StrEnum):
    """情报条目状态（术语表 §三；迁移与边界见 doc-02 §4.3）。"""

    LEAD = "lead"  # 线索：采集产出，未经审查
    CANDIDATE = "candidate"  # 候选：审查通过，待核实
    VERIFIED = "verified"  # 已核实：核实通过并完成评级
    UNDETERMINED = "undetermined"  # 存疑：核实无法完成，挂起待复核
    NOISE = "noise"  # 噪音：审查否决的终态
    REJECTED = "rejected"  # 否决：核实否决的终态


class ItemMode(enum.StrEnum):
    """情报条目采集方式。"""

    MANUAL = "manual"  # 人工提交（录入素材页）
    AUTOMATED = "automated"  # 自动拉取


class IntelligenceRequirementStatus(enum.StrEnum):
    """情报需求状态（术语表 §一；迁移与边界见 doc-02 §4.1）。"""

    DRAFT = "draft"  # 草稿：声明后待确认
    ACTIVE = "active"  # 激活：驱动采集
    PAUSED = "paused"  # 暂停：挂起，不驱动采集
    CLOSED = "closed"  # 关闭：需求满足或撤销


class ReviewDecisionEnum(enum.StrEnum):
    """审查决策（doc-06 §4）：通过为候选 / 否决为噪音。"""

    PASS = "pass"  # 通过：Lead → Candidate
    REJECT = "reject"  # 否决：Lead → Noise


class RejectionReasonEnum(enum.StrEnum):
    """审查否决理由（doc-06 §4）：不相关 / 重复 / 无效。

    本里程碑最简：仅产出 IRRELEVANT 与 INVALID；DUPLICATE 留枚举位以备事件同一性加厚。
    """

    IRRELEVANT = "irrelevant"  # 不相关：与激活情报需求无关
    DUPLICATE = "duplicate"  # 重复：同源纯重复（事件同一性加厚后启用）
    INVALID = "invalid"  # 无效：陈述不完整 / 非客观 / 纯评价


class VerificationOutcome(enum.StrEnum):
    """核实结果（doc-06 §5）：已核实 / 存疑。

    已核实：完成评级落账；存疑：核实无法完成挂起（可设复核期，本里程碑暂缓）。
    """

    VERIFIED = "verified"  # 已核实：Candidate → Verified
    UNDETERMINED = "undetermined"  # 存疑：Candidate → Undetermined


class FeedbackType(enum.StrEnum):
    """反馈七类型（术语表 §七、doc-02 §6）。"""

    VALID = "valid"  # 有效
    FACTUAL_ERROR = "factual_error"  # 事实错误
    DUPLICATE_NOISE = "duplicate_noise"  # 重复 / 噪音
    IRRELEVANT = "irrelevant"  # 不相关
    OUTDATED = "outdated"  # 过期
    RATING_DISPUTE = "rating_dispute"  # 评级异议
    REVIEW_DISPUTE = "review_dispute"  # 审查异议：不服审查否决，携理由重审


class SourceType(enum.StrEnum):
    """信源类型（doc-04 §1）。"""

    COMPANY = "company"  # 公司
    GOVERNMENT = "government"  # 政府
    ORGANIZATION = "organization"  # 组织
    MEDIA = "media"  # 媒体
    PERSON = "person"  # 人物
    OTHER = "other"  # 其他


class Medium(Base):
    """媒介：情报的获取场景，封闭小集合（术语表 §六）。"""

    __tablename__ = "medium"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Modality(Base):
    """载体：原始素材的物理形态（术语表 §六）。"""

    __tablename__ = "modality"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    pipeline: Mapped[str | None] = mapped_column(String(50))  # 处理管线：asr/ocr/parse；文字为空


class Source(Base):
    """信源：情报的发布主体（术语表 §六）。待确认信源不入正式池、不参与信用记账（decision-05）。"""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    type: Mapped[SourceType] = mapped_column(_sa_enum(SourceType))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    credit: Mapped[str | None] = mapped_column(String(1))  # 信源信用 A–F（信用记账归 IIH-01.06）

    outlets: Mapped[list["Outlet"]] = relationship(back_populates="source")
    credit_adjustments: Mapped[list["CreditAdjustment"]] = relationship(back_populates="source")


class Outlet(Base):
    """途径：主体的发布出口，归属唯一信源（术语表 §六）。"""

    __tablename__ = "outlet"
    __table_args__ = (UniqueConstraint("source_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    name: Mapped[str] = mapped_column(String(200))
    entry: Mapped[str | None] = mapped_column(Text)  # 采集入口：网址/RSS/账号/线下场景
    medium_id: Mapped[int | None] = mapped_column(ForeignKey("medium.id"))

    source: Mapped["Source"] = relationship(back_populates="outlets")
    medium: Mapped["Medium | None"] = relationship()


class LlmCall(Base):
    """LLM 调用计量（技术架构 §1）：智能体/对象/token/时间/模型。"""

    __tablename__ = "llm_call"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(50))  # 智能体（collector / reviewer / …）
    target: Mapped[str] = mapped_column(String(200))  # 调用对象（如 manual_submission）
    model: Mapped[str] = mapped_column(String(100))  # 模型标识
    prompt_tokens: Mapped[int]
    completion_tokens: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntelligenceItem(Base):
    """情报条目：陈述 + 溯源五要素 + 评级 + 状态 + 作废标记（doc-04 §1、术语表 §三）。"""

    __tablename__ = "intelligence_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement: Mapped[str] = mapped_column(Text)  # 陈述内容
    status: Mapped[ItemStatus] = mapped_column(
        _sa_enum(ItemStatus), default=ItemStatus.LEAD, index=True
    )
    rating: Mapped[str | None] = mapped_column(String(2))  # 情报评级，如 B2（核实后填）
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)  # 作废标记，正交于状态
    mode: Mapped[ItemMode] = mapped_column(_sa_enum(ItemMode), default=ItemMode.MANUAL, index=True)

    # 溯源五要素：载体 + 媒介 + 采集时间 + 原文快照 + 信源/途径归因
    modality_id: Mapped[int] = mapped_column(ForeignKey("modality.id"))
    medium_id: Mapped[int] = mapped_column(ForeignKey("medium.id"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_snapshot: Mapped[str | None] = mapped_column(Text)  # 原文快照：人工提交文本
    source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"), index=True)
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlet.id"))

    provenance_source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"))  # 出处信源
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 事件时间

    # 自动拉取路径专用（doc-06 §3 前置过滤）：内容指纹 + 原文链接 + 快照对象键
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    original_url: Mapped[str | None] = mapped_column(Text)
    snapshot_object_key: Mapped[str | None] = mapped_column(
        String(120)
    )  # 原始网页 HTML 对象键（MinIO）

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    modality: Mapped["Modality"] = relationship()
    medium: Mapped["Medium"] = relationship()
    source: Mapped["Source | None"] = relationship(foreign_keys=[source_id])
    outlet: Mapped["Outlet | None"] = relationship()
    provenance_source: Mapped["Source | None"] = relationship(foreign_keys=[provenance_source_id])
    provenance_nodes: Mapped[list["ProvenanceChainNode"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    verification_records: Mapped[list["VerificationRecord"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class IntelligenceRequirement(Base):
    """情报需求（doc-04 §1、doc-02 §4.1）：消费方声明的兴趣配置。

    本任务最简：name + content_spec + status。豁免「提出方」（单消费方前提，doc-07 §1）
    与「生效窗口」（范围外含调度节奏）——任务 comment 留痕豁免。
    """

    __tablename__ = "intelligence_requirement"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    content_spec: Mapped[str] = mapped_column(Text)  # 主题、关键词、信源偏好、时效要求等自由文本
    status: Mapped[IntelligenceRequirementStatus] = mapped_column(
        _sa_enum(IntelligenceRequirementStatus),
        default=IntelligenceRequirementStatus.DRAFT,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProvenanceChainNode(Base):
    """转引链节点（doc-03 §六）：一条情报的完整溯源路径节点。

    每个节点记一个信源引用；主条目 source_id/outlet_id 作为「出处信源」（最早引入陈述的信源），
    节点表存全部引用含出处信源本身。命中既有条目时仅追加节点，不新建条目（doc-06 §3 前置过滤）。
    """

    __tablename__ = "provenance_chain_node"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "source_id", "outlet_id", name="uq_node_per_item_source_outlet"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_item.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlet.id"))
    modality_id: Mapped[int] = mapped_column(ForeignKey("modality.id"))
    medium_id: Mapped[int] = mapped_column(ForeignKey("medium.id"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    original_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped["IntelligenceItem"] = relationship(back_populates="provenance_nodes")
    source: Mapped["Source"] = relationship(foreign_keys=[source_id])
    outlet: Mapped["Outlet | None"] = relationship(foreign_keys=[outlet_id])
    modality: Mapped["Modality"] = relationship()
    medium: Mapped["Medium"] = relationship()


class ReviewDecision(Base):
    """审查决策记录（doc-06 §4、doc-08 #8）：每次审查落一条，附依据。

    通过为候选（Lead → Candidate）：matched_requirement_id 必填，reason_type 为空。
    否决为噪音（Lead → Noise）：reason_type 必填，matched_requirement_id 为空。
    审查依据持久化以支撑可追溯（无溯源不落账）。
    """

    __tablename__ = "review_decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_item.id"), index=True)
    decision: Mapped[ReviewDecisionEnum] = mapped_column(_sa_enum(ReviewDecisionEnum))
    reason_type: Mapped[RejectionReasonEnum | None] = mapped_column(_sa_enum(RejectionReasonEnum))
    matched_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("intelligence_requirement.id")
    )
    rationale: Mapped[str] = mapped_column(Text)  # 审查依据
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped["IntelligenceItem"] = relationship(back_populates="review_decisions")
    matched_requirement: Mapped["IntelligenceRequirement | None"] = relationship(
        foreign_keys=[matched_requirement_id]
    )


class VerificationRecord(Base):
    """核实评级记录（doc-06 §5、doc-08 #8、doc-04 §1 推理记录）：每次核实落一条，附依据与公式版本。

    已核实（Candidate → Verified）：outcome=VERIFIED，N/R/credibility/rating 必填，
    formula_version 记公式版本。
    存疑（Candidate → Undetermined）：outcome=UNDETERMINED，N 仍记（已穿透统计），
    R/credibility/rating 为空。
    核实依据 + 公式版本持久化以支撑可追溯与可重放（无溯源不落账、变量与结论分离 decision-01）。
    """

    __tablename__ = "verification_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_item.id"), index=True)
    outcome: Mapped[VerificationOutcome] = mapped_column(_sa_enum(VerificationOutcome))
    independent_source_count: Mapped[int] = mapped_column(default=0)  # N：穿透转引链后的独立信源数
    source_reliability: Mapped[str | None] = mapped_column(String(1))  # R：A–F；VERIFIED 必填
    content_credibility: Mapped[int | None] = mapped_column()  # 1–6；VERIFIED 必填
    rating: Mapped[str | None] = mapped_column(String(2))  # 如 "B2"；VERIFIED 必填
    formula_version: Mapped[str | None] = mapped_column(String(50))  # 公式版本；UNDETERMINED 时为空
    rationale: Mapped[str] = mapped_column(Text)  # 核实依据
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped["IntelligenceItem"] = relationship(back_populates="verification_records")


class Feedback(Base):
    """反馈（doc-04 §1、doc-02 §6）：消费方对条目的类型化评价，经反馈路由分流。

    本任务最简：目标仅情报条目（命题反馈待命题实体落地）；豁免「评价方」
    （单消费方前提，doc-07 §1）——任务 comment 留痕。
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("intelligence_item.id"), index=True)
    feedback_type: Mapped[FeedbackType] = mapped_column(_sa_enum(FeedbackType))
    reason: Mapped[str] = mapped_column(Text)  # 理由：快捷反馈默认「快捷 · {类型}」
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped["IntelligenceItem"] = relationship(back_populates="feedbacks")


class CreditAdjustment(Base):
    """信用调整记录（doc-04 §2.3、decision-04）：信用通路反馈经归因落账的责任信源奖惩。

    归因结果即本行责任信源（可追溯）；反馈与调整一对一（unique）；
    score_after/grade_after/formula_version 为计算快照，同反馈历史重放得同信用值（可重放）。
    """

    __tablename__ = "credit_adjustment"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedback.id"), unique=True)
    delta: Mapped[int] = mapped_column()  # 奖惩分：有效 +1 / 事实错误 −2
    score_after: Mapped[float] = mapped_column()  # 半衰期累计分快照
    grade_after: Mapped[str] = mapped_column(String(1))  # 信源信用档快照 A–F
    formula_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="credit_adjustments")
    feedback: Mapped["Feedback"] = relationship()
