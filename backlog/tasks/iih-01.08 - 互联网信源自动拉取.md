---
id: IIH-01.08
title: 互联网信源自动拉取
status: To Do
assignee: []
created_date: '2026-09-11 08:38'
updated_date: '2026-09-11 08:38'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-01.07
references:
  - doc-06 §2/§3
  - doc-07 §2.2
parent_task_id: IIH-01
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要系统自动拉取已登记互联网信源的内容产出线索，以便日常省去人工盯信源的人力——监控闭环的核心价值点。

自动拉取链（doc-06 §2 定向、§3 采集、doc-07 §2.2 常驻监控）：定向智能体最简版按激活情报需求向已登记互联网途径派单 → fetcher 拉单页 → 采集智能体识别陈述、组装线索（溯源五要素齐备——信源=登记主体、途径=登记互联网途径）、执行前置指纹去重。与人工录入（IIH-01.01）产出的线索汇入同一审查入口。

范围外（后续里程碑加厚）：调度节奏（定时/事件触发）、池外自由探索、多途径编排、载体管线除网页外的解析。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 已登记信源 W 公司 · 官网（互联网途径，IIH-01.07）且情报需求已激活 When 系统自动拉取该信源 Then 产出线索提案（陈述、溯源五要素齐备——信源 W 公司、途径 官网·互联网、采集时间、原文链接、载体 网页），落账为「线索」态，进入审查
- [ ] #2 Given 拉取到与既有条目内容指纹相同的素材 When 采集前置过滤比对 Then 命中不进采集智能体，仅在既有条目转引链追加该信源引用
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
