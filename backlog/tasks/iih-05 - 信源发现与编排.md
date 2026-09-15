---
id: IIH-05
title: 信源发现与编排
status: To Do
assignee: []
created_date: '2026-09-15 03:45'
updated_date: '2026-09-15 12:31'
labels:
  - product
dependencies: []
references:
  - doc-01
  - decision-05
  - doc-06 §2
  - doc-06 §3
  - IIH-01.07
  - IIH-01.08
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要系统主动发现并把关新信源准入、对同一信源的多途径统一编排、采集调度可靠且可被事件即时触发，以便持续扩大有把关的信源覆盖，实现常驻监控的完整形态（doc-01 场景 1）。

现状：信源引入仅有通道一（人工登记直接入池，m-0 种子信源）；人工录入归因可产生待确认信源但无确认入口（decision-05 通道二未闭环）；途径仅在登记时建一条，无法为既有信源补途径；采集任务内存即时消费、不落账（doc-06 §2 暂缓项），采集只按频率定时触发。需求级节奏（频率/时效/生效窗口）已由 IIH-03.01 落地，不在本特性重复。

范围：
1. 待确认信源确认闭环：消费方确认入池或拒绝留痕（decision-05 准入把关）。
2. 池外自由探索与新信源发现：采集执行按比例探索池外，产出新信源发现提案，经确认入池（decision-05 通道二）。
3. 多途径登记与编排：同一信源补登记多个发布出口，一份信用与画像下覆盖全部出口。
4. 采集任务落账与事件触发：collection_task 落账（重试、消费审计）+ 事件触发采集。

范围外：多消费方信源准入分歧裁决；信源画像深度加工（立场偏差、独立性关联）；调度成本核算仪表盘。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
