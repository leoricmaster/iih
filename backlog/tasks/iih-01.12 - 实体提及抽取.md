---
id: IIH-01.12
title: 实体提及抽取
status: To Do
assignee: []
created_date: '2026-09-11 09:25'
labels:
  - pipeline
dependencies:
  - IIH-01.01
references:
  - doc-06 §3
  - doc-02 §3
  - doc-04 §1
  - decision-05
parent_task_id: IIH-01
type: feature
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为系统，我想要采集智能体自线索陈述抽取实体提及并落账，以便建立知识底座供图谱与检索使用。

doc-06 §3 采集智能体职责含「自陈述抽取实体提及（世界对象锚定）」，随情报条目新建提案落账（既有实体引用或新实体建立）。IIH-01.01 奠基阶段采集智能体只做信源/途径归因，实体提及抽取剥离承载，避免遗漏。实体提及挂载于情报条目，由采集智能体自陈述抽取（doc-02 §3 实体层、doc-04 §1 实体提及属性）；实体归一归审查智能体，归并既有实体走提案 + 消费方确认（doc-06 §4，参照 decision-05）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 线索陈述落账 When 采集智能体自陈述抽取实体提及 Then 实体提及随情报条目挂载落账，含原文依据（span/引文）与抽取提案溯源
- [ ] #2 Given 抽取识别出新实体 When 落账 Then 新实体随提及建立；既有实体则引用（归并走审查智能体提案 + 消费方确认）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
