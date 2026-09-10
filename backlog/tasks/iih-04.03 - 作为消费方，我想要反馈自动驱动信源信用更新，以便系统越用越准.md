---
id: IIH-04.03
title: 作为消费方，我想要反馈自动驱动信源信用更新，以便系统越用越准
status: To Do
assignee: []
created_date: '2026-09-10 12:51'
labels:
  - product
  - ledger
dependencies:
  - IIH-04.02
parent_task_id: IIH-04
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 2 消费反馈链的闭环 US（进化支柱 day-1 验证）：有效/事实错误反馈经信用归因（decision-08）定位到责任信源——转引链上最早引入该陈述的信源，如实转述者不受奖惩；信用计算器按 decision-04 公式更新信源信用分档。事实错误触发条目作废标记（级联传播深度本里程碑验证作废落账即可，后续加厚）。关联 decision-04/08、领域模型 doc-02 §6。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方对一条条目给「有效」反馈 When 信用归因执行 Then 定位到转引链最早引入该陈述的信源（出处信源），信用计算器按 decision-04 公式 +1 并更新分档，如实转载者不动
- [ ] #2 Given 消费方对一条条目给「事实错误」反馈 When 归因与计算执行 Then 责任信源 −2、条目打作废标记落账
- [ ] #3 Given 同一反馈历史 When 重放信用计算 Then 得同一信用值（可重放）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
