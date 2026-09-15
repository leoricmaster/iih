---
id: IIH-04.01
title: 「过期」反馈驱动采集配置学习通路
status: To Do
assignee: []
created_date: '2026-09-15 08:36'
labels:
  - product
  - pipeline
dependencies:
  - IIH-03.01
references:
  - doc-02 §6
  - IIH-03.01
parent_task_id: IIH-04
type: feature
ordinal: 17001
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要「过期」反馈能调整对应情报需求的采集频率与时效参数，以便系统按反馈自动校正采集节奏，避免持续抓取陈旧信息占用负载与费用。

现状：doc-02 §6 设计「过期」反馈路由去向为「采集频率、时效参数」学习通路，但 m-0 该通路未落地——「过期」反馈仅记录、不触发配置调整。

范围：「过期」反馈触发对应情报需求采集配置调整提案落账（频率/事件时效/生效窗口任一或组合，由反馈语义决定），下轮采集按新参数执行；调整经状态机执行器落账可追溯。

范围外：需求级采集配置字段本身（IIH-03.01 已承载）；其余反馈类型的学习通路（不相关/重复噪音/评级异议/审查异议）另立子任务；多消费方反馈分歧裁决。

关联：doc-02 §6（反馈类型与路由）、IIH-03.01（需求级采集配置字段与调度器）、IIH-01.05（m-0 反馈类型化入口奠基）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方对需求 A 的某条已核实条目给「过期」反馈 When 学习通路执行 Then 需求 A 的采集频率或事件时效参数调整提案落账，下轮采集按新参数执行（参数变更可见可追溯）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
