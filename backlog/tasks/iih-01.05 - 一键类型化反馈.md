---
id: IIH-01.05
title: 一键类型化反馈
status: To Do
assignee: []
created_date: '2026-09-11 01:41'
updated_date: '2026-09-11 08:59'
labels:
  - product
  - ui
milestone: m-0
dependencies:
  - IIH-01.04
references:
  - doc-02 §6
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要对条目一键给出类型化反馈，以便表达情报质量并驱动系统学习。

反馈入口（doc-07 §5、原型反馈交互）：收件箱或详情页对条目给六类型反馈，一步可达；快捷反馈默认理由「快捷 · {类型}」，Web 可补写，事实错误理由必填（信息架构 §5）；反馈经反馈路由按六类型分流（领域模型 §6）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方在条目卡片 When 一键选择「有效」 Then 反馈落账，默认理由「快捷 · 有效」，路由分流到信用通路
- [ ] #2 Given 消费方在详情页 When 选择「事实错误」但未填理由 Then 校验拦截，必填理由后方可提交
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
