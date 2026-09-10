---
id: IIH-03.02
title: 作为运维方，我想要审查智能体过滤线索，以便只有相关且有效的线索进入核实
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - pipeline
dependencies:
  - IIH-03.01
parent_task_id: IIH-03
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 1 生产链的第二环 US（doc-06 §4 审查智能体最简版）：审查智能体读线索、判相关性（对激活情报需求，本里程碑可硬关联或简化匹配）与有效性初筛，产出审查提案——通过为候选或否决为噪音附理由。事件同一性/实体归一本里程碑可最简或暂缓（单信源少冲突），后续加厚。关联领域模型 doc-02 §4.3。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条「线索」态条目且与激活情报需求相关 When 审查智能体判定通过 Then 状态迁移为「候选」，提案落账
- [ ] #2 Given 一条「线索」态条目且判定不相关 When 审查智能体否决 Then 状态迁移为「噪音」并附理由，提案落账
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
