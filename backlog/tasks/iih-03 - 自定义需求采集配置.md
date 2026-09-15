---
id: IIH-03
title: 自定义需求采集配置
status: To Do
assignee: []
created_date: '2026-09-15 09:17'
updated_date: '2026-09-15 09:20'
labels:
  - product
  - pipeline
milestone: m-1
dependencies: []
references:
  - doc-04 §1
  - doc-02 §4.1
  - decision-05
  - IIH-01
  - IIH-01.13
  - prototype/index.html
priority: high
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要为每个情报需求独立指定采集节奏、时效与覆盖的信源范围，以便按需求紧迫度差异化投入采集资源、控制负载与费用，并在需求列表一眼看见各需求的采集配置差异。

现状：m-0 所有激活需求共享全局调度间隔、覆盖全部已确认信源、无时效边界——列表里每个需求这三项都是同一个值，看不出差异，紧迫需求和高频需求被迫排队共享节奏。

范围：采集频率（可空=继承全局间隔）、事件时效边界（可空=不限，审查据此否决过期线索）、生效窗口（起止日期，可空=常驻，到期自动关闭）、信源绑定（可空=全部已确认信源，只绑定已确认信源，只影响自动拉取派单、人工录入不受限）；调度器按各需求独立参数分发采集任务，取代全局间隔 × 全激活需求笛卡尔积共用模式；情报需求列表与详情页展示四项配置。

范围外：「过期」反馈驱动配置调整的学习通路（DRAFT-10）；池外自由探索；多途径编排优化；调度成本核算仪表盘。

关联：doc-04 §1（情报需求字段含生效窗口）、doc-02 §4.1（需求状态机）、decision-05（待确认信源不入正式池）、IIH-01 范围外明列「调度节奏」、IIH-01.13 第六轮验收讨论留痕。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
