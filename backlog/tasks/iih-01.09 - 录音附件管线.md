---
id: IIH-01.09
title: 录音附件管线
status: To Do
assignee: []
created_date: '2026-09-11 09:24'
labels:
  - pipeline
  - ui
dependencies:
  - IIH-01.01
references:
  - doc-06 §3
  - doc-04 §1
  - doc-05 §3
  - prototype/index.html 录入素材页
parent_task_id: IIH-01
type: feature
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要上传录音附件经 ASR 转写产出线索，以便把会议/访谈录音送进流水线。

IIH-01.01 奠基阶段录入素材页只做文字载体；录音附件（ASR 转写）剥离承载，避免遗漏。录音载体经 ASR 管线转写为文字后，由采集智能体识别陈述、归因补记信源与途径、组装线索提案，与文字录入走同一条流水线（doc-06 §3）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方上传录音附件 When 经 ASR 转写为文字、采集智能体组装线索 Then 落账为「线索」态，溯源五要素齐备
- [ ] #2 Given 转写失败 When 管线处理 Then 不静默丢素材（落失败记录或重试），不产生半成品线索
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
