---
id: IIH-04.02
title: 作为消费方，我想要对条目一键给出类型化反馈，以便表达情报质量并驱动系统学习
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - ui
dependencies:
  - IIH-04.01
parent_task_id: IIH-04
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 2 消费反馈链的第二环 US（doc-07 §5 反馈入口）：消费方在收件箱或详情对条目给六类型反馈，一步可达。一键反馈默认理由「快捷 · {类型}」，Web 可补写，事实错误理由必填（decision-11）。反馈经反馈路由按六类型分流（领域模型 §6 路由表）。关联领域模型 doc-02 §6、decision-11。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方在条目卡片 When 一键选择「有效」 Then 反馈落账，默认理由「快捷 · 有效」，路由分流到信用通路
- [ ] #2 Given 消费方在详情页 When 选择「事实错误」但未填理由 Then 校验拦截，必填理由后方可提交
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
