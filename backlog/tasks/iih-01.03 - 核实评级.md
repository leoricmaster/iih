---
id: IIH-01.03
title: 核实评级
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 08:59'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-01.02
references:
  - doc-04 §2.1
  - doc-02 §5
  - doc-06 §5
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要已核实条目带二维评级，以便一眼判断情报可信度。

核实智能体最简版（doc-06 §5）：读候选、统计独立信源（穿透转引链，本里程碑单信源可简化）、按公式评内容可信度 1–6（数据设计 §2.1）、取信源画像可靠度 A–F 组装二维评级，落「已核实」。变量与结论分离：智能体测变量、公式出结论、公式版本记推理记录。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条「候选」态条目 When 核实智能体测得独立信源 N=1、出处信源可靠度 R=B Then 公式出内容可信度 2，组装评级 B2，状态迁移为「已核实」，公式版本记入推理记录
- [ ] #2 Given 一条「候选」态条目 When 核实无法完成 Then 状态迁移为「存疑」挂起（可设复核期）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
