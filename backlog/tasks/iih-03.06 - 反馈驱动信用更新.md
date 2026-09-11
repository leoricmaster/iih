---
id: IIH-03.06
title: 反馈驱动信用更新
status: To Do
assignee: []
created_date: '2026-09-11 01:41'
updated_date: '2026-09-11 01:42'
labels:
  - product
  - ledger
dependencies:
  - IIH-03.05
parent_task_id: IIH-03
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要反馈自动驱动信源信用更新，以便系统越用越准。

有效/事实错误反馈经信用归因（decision-08）定位责任信源——转引链上最早引入该陈述的信源，如实转述者不受奖惩；信用计算器按 decision-04 公式更新信源信用分档。事实错误触发条目作废标记（级联重估传播深度本里程碑验证作废落账即可，后续加厚）。关联 decision-04/08、doc-02 §6。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方对一条条目给「有效」反馈 When 信用归因执行 Then 定位到转引链最早引入该陈述的信源，信用计算器按 decision-04 公式 +1 并更新分档，如实转载者不动
- [ ] #2 Given 消费方对一条条目给「事实错误」反馈 When 归因与计算执行 Then 责任信源 −2、条目打作废标记落账
- [ ] #3 Given 同一反馈历史 When 重放信用计算 Then 得同一信用值（可重放）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
