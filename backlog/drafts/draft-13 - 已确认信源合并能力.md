---
id: DRAFT-13
title: 已确认信源合并能力
status: Draft
assignee: []
created_date: '2026-09-17 08:08'
labels:
  - product
dependencies: []
references:
  - doc-04 §2.3
  - decision-05
parent_task_id: IIH-06
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
IIH-06.02 验收发现缺口：两个已确认信源实际为同一主体时（如「中国工程机械信息网」与「工程机械信息网」），当前无合并能力——画像页改名撞既有已确认信源名即拦截，待确认→已确认并入路径已有但已确认之间合并缺。

现状：临时靠手工 SQL 迁移条目/节点/途径/IR 绑定/信用调整 + 加别名 + 删源行；无留痕、无校验、易漏迁移点。

长期方案：状态机加 SourceMergeProposal（payload: from_id, to_id），处理器复用 _merge_into_confirmed 的迁移逻辑并放开 confirmed 前置；画像页加入口（选目标信源，可能需 modal）。配套：信源库页加「已确认信源两两相似查重提示」帮助发现需合并的对（沿用 difflib ≥ 0.7）。

References: doc-04 §2.3, decision-05, IIH-06.02
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
