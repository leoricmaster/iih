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
    original_snapshot: Mapped[str] = mapped_column(Text)  # 原文快照 / 链接
    source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"), index=True)
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlet.id"))

    provenance_source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"))  # 出处信源
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 事件时间

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    modality: Mapped["Modality"] = relationship()
    medium: Mapped["Medium"] = relationship()
    source: Mapped["Source | None"] = relationship(foreign_keys=[source_id])
    outlet: Mapped["Outlet | None"] = relationship()
    provenance_source: Mapped["Source | None"] = relationship(foreign_keys=[provenance_source_id])
