"""定向智能体 Director（doc-06 §2）· 需求级采集配置版（IIH-03.01）。

激活情报需求 × 已确认信源互联网途径 → 内存 CollectionTask 列表，按各 IR 独立参数分发：
1. 生效窗口到期扫描：valid_until ≤ today 的激活 IR 触发自动关闭（落账 Close 提案）
2. 频率 due 过滤：未到采集节奏的 IR 跳过本轮（last_collected_at + 频率 > now）
3. 信源绑定过滤：IR 绑定信源 → 仅派单到这些信源的互联网途径；空 → 全部已确认

IIH-06.01 通路反转：探索常驻——每个 due 需求无条件 +1 个探索任务（不绑定途径，
信源池为空亦派，解冷启动）；探索发现的新信源经条目归因进待确认队列（decision-05）。

本里程碑不调 LLM——仅做确定性派单；采集任务不落账（decision-08 暂），
Director 产出物为内存 dataclass，由调用方消费。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from iih.config import get_settings
from iih.ledger.duration import parse_duration_to_seconds
from iih.ledger.models import (
    IntelligenceRequirement,
    IntelligenceRequirementStatus,
    Outlet,
    Source,
    SourceType,
)
from iih.ledger.proposal import (
    IntelligenceRequirementClosePayload,
    IntelligenceRequirementCloseProposal,
)
from iih.ledger.state_machine import StateMachineExecutor


@dataclass(frozen=True)
class CollectionTask:
    """定向智能体任务化产物（内存对象，不落账）：常规途径采集任务。

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


@dataclass(frozen=True)
class ExplorationTask:
    """探索任务（内存对象，不落账）：不绑定途径的池外检索式探索。

    content_spec 为检索词来源（探索执行时 LLM 提取关键词）。
    """

    requirement_id: int
    requirement_name: str
    content_spec: str


class Director:
    """定向智能体执行器（判断层）：无状态、输出内存任务列表。"""

    AGENT_NAME = "director"

    def __init__(self, session: Session) -> None:
        self.session = session

    def propose_tasks(self) -> tuple[list[CollectionTask], list[ExplorationTask]]:
        """按各 IR 独立参数派单：到期关闭 → due 过滤 → 信源绑定过滤 → 笛卡尔积 + 探索常驻。

        常规任务范围：仅 medium.code='internet' 的途径；信源须 confirmed=True（decision-05）。
        途径 entry 为空则跳过——无法派单。探索任务：每个 due 需求无条件一个。
        """
        self._auto_close_expired()

        active_irs = list(
            self.session.scalars(
                select(IntelligenceRequirement).where(
                    IntelligenceRequirement.status == IntelligenceRequirementStatus.ACTIVE
                )
            )
        )
        if not active_irs:
            return [], []

        now = datetime.now(UTC)
        due_irs = [ir for ir in active_irs if self._is_due(ir, now)]
        if not due_irs:
            return [], []

        all_internet_outlets = list(
            self.session.scalars(
                select(Outlet)
                .join(Source, Outlet.source_id == Source.id)
                .where(Source.confirmed.is_(True))
                .where(Outlet.medium.has())
            )
        )
        internet_outlets = [
            o
            for o in all_internet_outlets
            if o.medium is not None and o.medium.code == "internet" and o.entry
        ]

        tasks: list[CollectionTask] = []
        explorations: list[ExplorationTask] = []
        for ir in due_irs:
            for outlet in self._outlets_for_ir(ir, internet_outlets):
                tasks.append(
                    CollectionTask(
                        requirement_id=ir.id,
                        requirement_name=ir.name,
                        outlet_id=outlet.id,
                        source_id=outlet.source.id,
                        source_name=outlet.source.name,
                        source_type=outlet.source.type,
                        outlet_name=outlet.name,
                        url=outlet.entry or "",
                    )
                )
            explorations.append(
                ExplorationTask(
                    requirement_id=ir.id,
                    requirement_name=ir.name,
                    content_spec=ir.content_spec,
                )
            )
        return tasks, explorations

    def _auto_close_expired(self) -> None:
        """生效窗口到期自动关闭：valid_until ≤ today 的激活 IR 落账 Close 提案。

        关闭由确定性系统触发（非智能体判断），复用既有 Close 提案；
        rationale 标「生效窗口到期自动关闭」便于审计。
        """
        today = datetime.now(UTC).date()
        expired_irs = list(
            self.session.scalars(
                select(IntelligenceRequirement).where(
                    IntelligenceRequirement.status == IntelligenceRequirementStatus.ACTIVE,
                    IntelligenceRequirement.valid_until.is_not(None),
                    IntelligenceRequirement.valid_until <= today,
                )
            )
        )
        executor = StateMachineExecutor()
        for ir in expired_irs:
            try:
                executor.execute(
                    IntelligenceRequirementCloseProposal(
                        payload=IntelligenceRequirementClosePayload(requirement_id=ir.id),
                        rationale="生效窗口到期自动关闭",
                    ),
                    session=self.session,
                )
            except Exception:  # noqa: BLE001 - 自动关闭失败不阻断派单主流程
                pass

    def _is_due(self, ir: IntelligenceRequirement, now: datetime) -> bool:
        """IR 是否到采集节奏：last_collected_at + 频率 ≤ now。

        频率非空：用解析秒数；频率为空：用全局 pipeline_interval_seconds。
        last_collected_at 为空（从未采集）：始终 due。
        """
        if ir.last_collected_at is None:
            return True
        freq_seconds = (
            parse_duration_to_seconds(ir.collection_frequency)
            if ir.collection_frequency
            else get_settings().pipeline_interval_seconds
        )
        if freq_seconds is None or freq_seconds <= 0:
            return True
        # last_collected_at 可能是 naive（旧数据）或 aware；统一按 UTC 比较
        last = ir.last_collected_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return now - last >= timedelta(seconds=freq_seconds)

    def _outlets_for_ir(
        self, ir: IntelligenceRequirement, all_outlets: list[Outlet]
    ) -> list[Outlet]:
        """IR 的可用途径：绑定信源则仅取这些信源的互联网途径；空则全部。

        信源绑定只影响自动拉取派单（人工录入不受限，AC#2）。
        """
        if not ir.sources:
            return all_outlets
        bound_source_ids = {s.id for s in ir.sources}
        return [o for o in all_outlets if o.source_id in bound_source_ids]
