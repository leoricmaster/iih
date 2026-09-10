---
id: IIH-03.03
title: 作为消费方，我想要已核实条目带二维评级，以便一眼判断情报可信度
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - pipeline
dependencies:
  - IIH-03.02
parent_task_id: IIH-03
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 1 生产链的第三环 US（doc-06 §5 核实智能体最简版）：核实智能体读候选、统计独立信源（穿透转引链，本里程碑单信源可简化）、按公式评内容可信度 1–6（数据设计 §2.1）、取信源画像可靠度 A–F 组装二维评级，落「已核实」。变量与结论分离：智能体测变量、公式出可信度、公式版本记推理记录。关联数据设计 doc-04 §2.1、领域模型 doc-02 §5。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条「候选」态条目 When 核实智能体测得独立信源 N=1、出处信源可靠度 R=B Then 公式出内容可信度 2，组装评级 B2，状态迁移为「已核实」，公式版本记入推理记录
- [ ] #2 Given 一条「候选」态条目 When 核实无法完成 Then 状态迁移为「存疑」挂起（可设复核期）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
