---
id: DRAFT-10
title: 「过期」反馈驱动采集配置学习通路
status: Draft
assignee: []
created_date: '2026-09-15 08:36'
labels:
  - product
  - pipeline
dependencies: []
references:
  - doc-02 §6
  - DRAFT-09
parent_task_id: IIH-01
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要「过期」反馈能调整对应情报需求的采集频率与时效参数，以便系统按反馈自动校正采集节奏，避免持续抓取陈旧信息占用负载与费用。

doc-02 §6 设计：「过期」反馈路由去向为「采集频率、时效参数」学习通路。本单落地该通路——反馈触发需求采集配置调整提案落账，下轮采集按新参数执行。

范围外：需求级采集配置字段本身（生效窗口、采集频率、需求-信源绑定）属 DRAFT-09；池外自由探索、智能体迭代通路（审查/核实收紧）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方对需求 A 的某条已核实条目给「过期」反馈 When 学习通路执行 Then 需求 A 的采集频率或时效参数调整提案落账，下轮采集按新参数执行（参数可见可追溯）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
