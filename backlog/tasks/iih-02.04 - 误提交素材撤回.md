---
id: IIH-02.04
title: 误提交素材撤回
status: To Do
assignee: []
created_date: '2026-09-15 06:58'
labels:
  - product
  - ui
dependencies:
  - IIH-01.01
references:
  - doc-02 §4.3
  - doc-07 §2.3
  - IIH-01.13
parent_task_id: IIH-02
type: feature
ordinal: 15004
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要撤回误提交的素材，以便错录入的线索在进入审查前就能下撤，不必麻烦进库清数据。

现状：m-0 作废仅限已核实条目经「事实错误」反馈触发（连带信用扣减）；线索/候选/存疑/噪音态条目一旦落账无用户可操作的下撤途径，误提交只能进库清数据。

范围：人工提交的未核实态条目（线索/候选/存疑/噪音）可由提交人撤回；撤回留痕（软删 vs 状态迁移待 plan 裁决），不影响已核实条目的作废通路（事实错误反馈）与信用记账。

范围外：已核实条目的撤回（继续走事实错误反馈）；自动拉取条目的撤回（无提交人概念）。

关联：doc-02 §4.3（条目状态机）、doc-07 §2.3（录入素材页）、IIH-01.13 验收发现的缝隙留痕。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方误提交一条线索 When 在录入素材页或条目详情触发撤回 Then 该条目从流水线下撤、不再出现在收件箱与条目列表，撤回操作留痕可追溯
- [ ] #2 Given 一条已进入审查的候选条目 When 提交人撤回 Then 撤回生效，已产生的审查记录保留为留痕（不抹除历史）
- [ ] #3 Given 运维方尝试撤回一条已核实条目 When 触发 Then 拦截并提示「已核实条目请走事实错误反馈」
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
