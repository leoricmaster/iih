---
id: IIH-05.01
title: 待确认信源确认闭环
status: To Do
assignee: []
created_date: '2026-09-15 12:31'
labels:
  - product
dependencies: []
references:
  - decision-05
  - doc-04 §1
  - IIH-01.07
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 18002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要对人工录入归因产生的待确认信源逐一确认入池或拒绝，以便只有经我把关的信源进入信源库参与采集、画像与信用记账（decision-05 准入把关）。

现状：人工录入素材的溯源归因已能新建待确认信源（仅作记录，不入库、不建画像、不记账）；登记提案的记账层落账已支持确认入池（已确认态 + 初始信用档），但 Web 无确认入口——信源库、收件箱、条目详情、信源画像四处挂着「确认功能即将上线」占位。

范围：信源库对待确认信源的确认/拒绝入口（确认时给定初始信用档）；确认后入信源库、建画像、可被情报需求绑定与调度派单；拒绝留痕不入池；替换全部确认占位文案。

范围外：采集发现的新信源发现提案的确认（归池外自由探索单，确认入口复用本单）；确认后人工设档与反馈累计分归一（IIH-04.02）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 待确认信源 S（人工录入归因产生）When 消费方在信源库确认并给定初始信用档 Then S 进入信源库（已确认态）、建立画像、可被情报需求绑定与调度派单
- [ ] #2 Given 待确认信源 S When 消费方拒绝 Then S 不入信源库、留痕（拒绝记录可见），已归因到 S 的既有条目不受影响
- [ ] #3 Given 信源 S 尚未确认 When 调度器与记账运行 Then S 不参与派单、不建画像、不参与信用记账（decision-05 边界保持）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 全部「确认功能即将上线」占位替换为确认入口（信源库/收件箱/条目详情/信源画像）
<!-- DOD:END -->
