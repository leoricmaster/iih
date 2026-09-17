---
id: IIH-06.03
title: 信源画像页交互重构与 Outlet 简化
status: Done
assignee: []
created_date: '2026-09-17 09:01'
updated_date: '2026-09-17 15:11'
labels:
  - product
dependencies: []
references:
  - decision-05
  - doc-02 §80
  - doc-03 §163-§175
  - doc-07 §28
parent_task_id: IIH-06
type: feature
ordinal: 23002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
IIH-06 日常使用反馈继续。画像页交互散乱：主体改名常驻 input、别名只能加删不能改名、信用 select 常驻、途径三列只读——四种不同形态缺统一编辑态。Outlet 字段过度建模：非互联网途径 entry 永远为空、medium/is_internet 在 Outlet 上仅服务于『是否可采集』一种分支判断。

本任务整合：
①统一编辑态：显式编辑按钮进入、单端点 /sources/{id}/edit 批量保存、取消回到只读。
②别名补改名能力（inline 可改文字），与主体对齐。
③信用档 select → segmented control（A–F 或不设）。
④途径 Outlet 术语退役，收缩为**采集入口 Entry**（id/source_id/entry，(信源, 入口) 唯一）：非互联网途径（会议讨论、行业展会等）无地址不成行，线下归因靠条目级 medium；画像页/信源库只剩采集入口列表（URL / RSS / 账号 ID）。
⑤IntelligenceItem.outlet_id、ProvenanceChainNode.outlet_id 删除，转引链节点按 (条目, 信源) 去重，溯源要素收敛为信源 × 媒介 × 载体 × 时间 + 原文快照；Medium 表保留供 IntelligenceItem/Material 使用。
⑥『参与条目』默认折叠，编辑态不展示。
⑦不开新 decision，直接修订 decision-05（修订 2），同步 doc-02 ER 图、doc-03 术语表（采集入词汇目 + 补别名/主体词目）。

Outlet 简化属 decision-05 范围内演进，不新开 ADR，按 feedback 规则修订原 ADR + 同步文档。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 画像页编辑/只读两态切换正常，单端点 /sources/{id}/edit 承载改名/别名/信用/采集入口批量保存
- [x] #2 别名可改名（inline 改文字），改名不留档（按 IIH-06.02 规则）
- [x] #3 信用档显示为 segmented control（A–F + 不设），当前档高亮
- [x] #4 画像页/信源库途径区替换为采集入口列表（URL / RSS / 账号 ID 单列）；线下场景不建入口
- [x] #5 Outlet 全量退役为 Entry（id/source_id/entry），IntelligenceItem / ProvenanceChainNode 去 outlet 引用；迁移可逆；本地门禁含 alembic upgrade/downgrade
- [x] #6 『参与条目』默认折叠，点击可展开
- [x] #7 decision-05 修订 2 落账；doc-02 ER 边同步；doc-03 采集入词汇目 + 补别名词目/主体词目
- [x] #8 原型 prototype/index.html 同步编辑态、segmented、采集入口口径
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
验证：pytest 360 passed；ruff/format/mypy 绿；alembic upgrade→downgrade -1→upgrade head 三段可逆（修复 downgrade 漏 drop uq_node_per_item_source）；Docker 重建走查五页零途径/outlet 残留，编辑态+segmented+采集入口正常。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
途径 Outlet 退役为采集入口 Entry（id/source_id/entry），条目与转引链去途径引用；画像页统一编辑态（主体/别名/信用 segmented/采集入口）。经 pytest 360、alembic 三段可逆、Docker 走查验证，用户验收通过。
<!-- SECTION:FINAL_SUMMARY:END -->
