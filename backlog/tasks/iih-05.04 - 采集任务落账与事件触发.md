---
id: IIH-05.04
title: 采集任务落账与事件触发
status: To Do
assignee: []
created_date: '2026-09-15 12:32'
labels:
  - product
  - pipeline
dependencies: []
references:
  - doc-06 §2
  - IIH-03.01
  - IIH-04.01
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 21002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要派出的采集任务有据可查、失败可重试，且新建需求等事件能即时触发采集，以便采集可靠可审计、新需求不必干等下个调度周期。

现状：采集任务内存即时消费、不落账（doc-06 §2 暂缓项——待引入持久化调度再建表）：抓取失败该轮即丢、无重试，也无「派了什么、执行了什么」的账可查；采集仅按需求频率定时触发。需求级节奏（频率/时效/生效窗口）已由 IIH-03.01 落地，本单承接调度残部。

范围：采集任务落账（派单记录、执行结果、失败重试、消费审计，doc-06 §2 预留的 collection_task）；事件触发采集——新建情报需求落账激活后立即首轮采集；「过期」反馈重采的触发端衔接 IIH-04.01。前置裁决：途径级节奏差异化是否纳入本单（建议不纳入，途径画像已含节奏设计）。

范围外：调度成本核算仪表盘；多消费者并发调度；池外探索的任务化（归池外自由探索单）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 调度器派单 When 采集执行 Then 采集任务落账记录目标途径、检索参数与执行结果（成功/失败），派发与执行全程可审计
- [ ] #2 Given 采集任务执行失败 When 重试条件满足 Then 任务按策略重试，重试历史留痕
- [ ] #3 Given 消费方新建情报需求 When 需求落账为激活 Then 首轮采集即时触发，无需等待首个调度周期
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
