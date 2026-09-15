---
id: IIH-05.03
title: 多途径登记与编排
status: To Do
assignee: []
created_date: '2026-09-15 12:31'
labels:
  - product
dependencies: []
references:
  - doc-04 §1
  - doc-06 §2
  - IIH-01.07
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 20002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要为已确认信源补登记多个发布出口（官网/公众号/RSS 等）并统一编排盯守，以便同一主体一份信用与画像之下，采集覆盖其全部出口。

现状：登记信源仅新建主体 + 首条互联网途径，为既有主体补途径在 m-0 明确留待后续；调度派单与条目溯源已按途径维度工作，仅缺补途径的登记与管理入口。

范围：为既有已确认信源补登记途径（名称/入口/媒介，同信源内途径名唯一），经状态机校验落账；信源画像展示全部途径；调度对全部途径派单、条目溯源归因到具体途径。前置裁决：新媒介类型引入的论证流程（doc-01 自部署组件最少化前提）——先只放开既有媒介，或一并定论证规则。

范围外：途径级采集节奏差异化（途径画像的更新节奏字段已含设计，本单不实现节奏配置）；线下途径的采集执行；信源合并与拆分。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 已确认信源 S 已有官网途径 When 消费方为 S 补登记公众号途径（媒介=互联网）Then 落账成功，信源画像展示两条途径，调度对两条途径独立派单，条目溯源归因到具体途径
- [ ] #2 Given 补登记途径 When 途径名与该信源既有途径重复或字段缺失 Then 状态机驳回并回显原因，不落账
- [ ] #3 Given 信源 S 拥有多条途径 When 信用记账运行 Then 信源信用与画像仍按主体一份，不按途径拆分
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
