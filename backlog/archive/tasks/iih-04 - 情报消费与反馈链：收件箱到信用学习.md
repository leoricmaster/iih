---
id: IIH-04
title: 情报消费与反馈链：收件箱到信用学习
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - ledger
  - ui
milestone: m-0
dependencies:
  - IIH-03
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
端到端 Feature（特性条目，可写 release notes）：消费方在收件箱浏览已核实情报、给类型化反馈，反馈经路由分流、有效/事实错误经信用归因落到责任信源、信用计算器更新信源信用分档。这是最小闭环的消费半环——情报被消费、反馈回流驱动系统变聪明（进化支柱 day-1 验证）。端到端贯穿：收件箱可见→反馈→信用归因→信用更新。关联领域模型 doc-02 §6、信息架构 doc-07 §5、decision-04/08/11。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条已核实条目送达收件箱 When 消费方给「有效」反馈 Then 信用归因定位责任信源、信用计算器按 decision-04 更新分档（端到端验收）
- [ ] #2 Given 一条已核实条目 When 消费方给「事实错误」反馈并填理由 Then 条目打作废标记、责任信源信用扣减、触发级联重估（本里程碑验证作废落账即可）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
