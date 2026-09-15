---
id: IIH-05.02
title: 池外自由探索与新信源发现
status: To Do
assignee: []
created_date: '2026-09-15 12:31'
labels:
  - product
dependencies:
  - IIH-05.01
references:
  - decision-05
  - doc-06 §3
  - IIH-01.08
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 19002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要采集执行时按配置比例探索监控池外、上报发现的新信源，以便不主动搜索也能持续发现值得纳入的新信源，经我确认后扩大信源覆盖（decision-05 通道二）。

现状：采集智能体仅执行派单任务，无池外探索；新信源发现提案类型在 doc-06 §3 已设计、未实现；待确认队列与确认入口由待确认信源确认闭环单建立。

范围：采集智能体执行采集任务时按配置比例做池外自由探索；发现的新信源产出新信源发现提案（含发现来源与依据），进入待确认队列，经确认入口入池，与人工归因产生的待确认信源同通路。前置裁决：探索判断归采集智能体（doc-06 现状）或定向智能体加厚；探索比例的配置粒度（全局起步或需求级）。

范围外：探索方向的人工引导（研究课题联动）；新信源画像自动生成；信源库既有信源的相似去重提示。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 池外探索开启（比例大于 0）When 采集智能体执行采集任务 Then 按配置比例执行池外探索，发现的新信源产出新信源发现提案进入待确认队列
- [ ] #2 Given 新信源发现提案 When 消费方经确认入口确认 Then 该信源入信源库并可被情报需求绑定与调度派单
- [ ] #3 Given 新信源发现提案未经确认 When 调度与记账运行 Then 该信源不入信源库、不建画像、不参与信用记账（decision-05）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 探索比例默认值为 0，不影响既有采集行为；比例配置不经改代码可调
<!-- DOD:END -->
