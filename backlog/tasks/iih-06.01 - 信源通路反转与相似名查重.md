---
id: IIH-06.01
title: 信源通路反转与相似名查重
status: In Progress
assignee:
  - '@zhangyunfeng'
created_date: '2026-09-17 04:51'
updated_date: '2026-09-17 05:05'
labels:
  - product
dependencies: []
parent_task_id: IIH-06
type: feature
ordinal: 23002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
产品经一段时间实际使用后，交互流程调整需求的归置处。目标模型（2026-09-17 用户裁决方向）：先有情报，信源由情报归因识别——提出需求 → 派探索任务（不必绑定信源）→ 抓网页抽情报陈述落条目 → 条目归因识别未登记信源进待确认队列 → 确认设信用档、带 URL 建途径 → 转正为常规采集。已识别方向：①信源通路反转——人工登记入口下线（decision-05 通道一），探索改为产出情报条目而非只归因信源名，并支持独立触发（需求无绑定信源/信源池为空时派纯探索任务，解冷启动）；人工登记与「先找信源」式探索相关实现（SourceRegisterProposal、SourceDiscoveryProposal、现行 _explore_outside_pool）拟废弃清理，连带修订 decision-05 与 doc-04/06/07。②待确认信源相似名查重——提案与确认时识别既有近似信源（如「中国工业报」与「中国工业报社」），避免重复入池。拆分与排序届时裁决。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
①通路反转（先行）：1. Director 派单改造——每轮每 due 需求无条件 +1 探索任务（ExplorationTask：requirement_id/name/content_spec），冷启动即途径为零的自然特例；explore_ratio 字段删除（模型+表单+alembic 迁移）。2. Collector 新增 explore()：关键词→Tavily（排除信源池全部途径域）→LLM 选链→fetch→指纹去重→一次 LLM 抽陈述+归因→IntelligenceItemNewProposal（AUTOMATED、原文链接+快照对象、归因新信源带 discovered_entry 进待确认）；废弃 _explore_outside_pool。3. 状态机统一归因解析：AUTOMATED 撤销「信源已确认+途径已登记」边界，与 MANUAL 同路径（未知名建待确认）；废弃 SourceRegisterProposal/SourceDiscoveryProposal 两处理器；seed 改直接 ORM 铺底。4. Web：信源库页登记表单下线；需求表单/详情删探索比例。5. 修订 decision-05（草案先呈用户）、doc-04/06/07、术语表。6. 测试改写（collector/state_machine/web/director）。②相似名查重（①验收后）：difflib 归一化相似度，待确认行渲染近似既有信源提示+点选填名走既有并入路径，不自动归并。
<!-- SECTION:PLAN:END -->
