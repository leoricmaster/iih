---
id: IIH-01.02
title: 线索审查过滤
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 03:11'
labels:
  - product
  - pipeline
dependencies:
  - IIH-01.01
references:
  - doc-02 §4.3
  - doc-06 §4
parent_task_id: IIH-01
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要审查智能体过滤线索，以便只有相关且有效的线索进入核实。

审查智能体最简版（doc-06 §4）：读线索、判相关性（对激活情报需求，本里程碑硬关联或简化匹配）与有效性初筛，产出审查提案——通过为候选、否决为噪音附理由。事件同一性/实体归一本里程碑最简或暂缓（单信源少冲突），后续加厚。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条「线索」态条目且与激活情报需求相关 When 审查智能体判定通过 Then 状态迁移为「候选」，提案落账
- [ ] #2 Given 一条「线索」态条目且判定不相关 When 审查智能体否决 Then 状态迁移为「噪音」并附理由，提案落账
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
