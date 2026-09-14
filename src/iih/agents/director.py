"""定向智能体 Director（doc-06 §2）· 最简版。

激活情报需求 × 已确认信源的互联网途径 → 内存 CollectionTask 列表。
本里程碑不调 LLM——仅做确定性笛卡尔积；检索参数匹配、采集节奏、池外探索留待后续。
采集任务不落账（decision-08 暂），Director 产出物为内存 dataclass，由调用方消费。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.ledger.models import (
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Outlet,
    Source,
    SourceType,
)


@dataclass(frozen=True)
class CollectionTask:
    """定向智能体任务化产物（内存对象，不落账）。

    检索参数最简：无关键词过滤；URL 取自途径 entry。
    """

    requirement_id: int
    requirement_name: str
    outlet_id: int
    source_id: int
    source_name: str
    source_type: SourceType
    outlet_name: str
    url: str


class Director:
    """定向智能体执行器（判断层）：无状态、输出内存任务列表。"""

    AGENT_NAME = "director"

    def __init__(self, session: Session) -> None:
        self.session = session

    def propose_tasks(self) -> list[CollectionTask]:
        """激活 IR × 已确认信源互联网途径 → 采集任务笛卡尔积。

        范围：仅 medium.code='internet' 的途径；信源须 confirmed=True（decision-05）。
        途径 entry 为空则跳过——无法派单。
        """
        active_irs = list(
            self.session.scalars(
                select(IntelligenceRequirement).where(
                    IntelligenceRequirement.status == IntelligenceRequirementStatus.ACTIVE
                )
            )
        )
        if not active_irs:
            return []

        outlets = list(
            self.session.scalars(
                select(Outlet)
                .join(Source, Outlet.source_id == Source.id)
                .where(Source.confirmed.is_(True))
                .where(Outlet.medium.has())  # medium_id 非空
            )
        )
        internet_outlets = [
            o for o in outlets if o.medium is not None and o.medium.code == "internet"
        ]

        tasks: list[CollectionTask] = []
        for ir in active_irs:
            for outlet in internet_outlets:
                if not outlet.entry:
                    continue
                tasks.append(
                    CollectionTask(
                        requirement_id=ir.id,
                        requirement_name=ir.name,
                        outlet_id=outlet.id,
                        source_id=outlet.source.id,
                        source_name=outlet.source.name,
                        source_type=outlet.source.type,
                        outlet_name=outlet.name,
                        url=outlet.entry,
                    )
                )
        return tasks
