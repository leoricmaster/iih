---
id: IIH-03
title: 情报条目生产链：录入到已核实入库
status: To Do
assignee: []
created_date: '2026-09-10 12:49'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-02
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
端到端 Feature（特性条目，可写 release notes）：运维方人工录入素材，经审查智能体放行、核实智能体评级，产出带二维评级的已核实情报条目入库。这是最小闭环的生产半环——把世界说了什么变成可读、可溯源、带评级的情报。消费方随后可消费（消费半环在 Feature 2）。端到端贯穿：录入→审查→核实评级→入库，每步提案落账。关联智能体规约 doc-06 §3/§4/§5、领域模型 doc-02 §4.3、信息架构 doc-07 §2.3。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方录入一条线索 When 经审查通过、核实评级 Then 收件箱可见一条带二维评级的已核实条目（端到端验收）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
