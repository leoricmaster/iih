"""提案契约（技术架构 §5）：智能体对记账层的写入一律为提案——类型/产出/依据/溯源/公式版本。"""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel

from iih.ledger.models import ItemMode, SourceType


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
