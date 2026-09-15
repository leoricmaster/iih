---
id: DRAFT-05
title: 事件合并印证
status: Draft
assignee: []
created_date: '2026-09-15 03:45'
labels:
  - product
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
多信源报道同一事件时正确合并，独立信源计数与转载链穿透可信（decision-02 事件级合并完整落地）。

范围轮廓：
- 事件同一性判定：跨条目识别同一事件（IIH-01.03 最简版留待加厚项）
- 合并印证：命中既有条目并入，独立信源计数随之更新
- 转载链穿透完整版：多处转载只计一个独立信源（IIH-01.08 已落指纹命中追链节点）

现状边界：MVP 单信源，N 统计已简化；转引链数据结构就位但场景单一。

明细约束：故事按端到端能力拆，不按技术层拆（archive 旧层级切片已废弃）；术语从 doc-03。

开放问题：事件同一性判断归核实还是审查智能体（doc-06 归属确认）；内容指纹与语义合并的边界。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
