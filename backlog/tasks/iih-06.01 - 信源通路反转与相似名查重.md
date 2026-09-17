---
id: IIH-06.01
title: 信源通路反转与相似名查重
status: To Do
assignee: []
created_date: '2026-09-17 04:51'
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
