---
id: IIH-06.07
title: 信源库页面精简
status: In Progress
assignee: []
created_date: '2026-09-18 05:02'
updated_date: '2026-09-18 05:06'
labels: []
dependencies: []
references:
  - doc-07 §3（信源库页面行——IA 对象描述不变，本次为呈现层精简）
parent_task_id: IIH-06
type: feature
ordinal: 32002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为日常使用者，我在信源库列表与信源画像页看到精简的列与短标题、且各区块标题字重一致，以便更快扫读定位信源信用与画像信息。

用户使用反馈（2026-09-18）：列表「采集入口」「状态」两列不需要——入口管理归宿在画像页，待确认信源另有专区；画像页「信源信用/采集入口/参与条目」标题过长。改后发现折叠区块「情报」标题比「主体/信用/入口」细：details.box>summary 未设 font-weight（浏览器默认常规体），h2 为浏览器默认粗体——系统性差异，条目详情页五个折叠区块同受影响，一并拉齐。术语表（doc-03）正本不变：界面用短标签，文档仍用全称术语。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 信源库列表不再展示「采集入口」「状态」列，表头为：信源 / 类型 / 信源信用 / 历史反馈
- [x] #2 信源画像页查看态与编辑态区块标题用短名：信用 / 入口 / 情报
- [x] #3 全站折叠区块标题（details.box>summary）与区块标题（h2）字重一致，不再偏细
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. sources.html：删两列，表头 信源/类型/信源信用/历史反馈，空态 colspan=4。
2. source_detail.html：查看态与编辑态五处标题缩短（信源信用→信用、采集入口→入口×2、参与条目→情报）；按钮文案（加/删采集入口）与空态提示不在范围。
3. app.css：details.box>summary 补 font-weight:700，对齐 .box>h2 的默认粗体；条目详情页折叠区块同步生效。
4. tests/test_web.py：三处断言随标题（<h2>信用）。
5. 验证：uv run pytest -q 全量；compose 重建部署 + 截图自查（列表列、详情标题、字重）。
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
验证（2026-09-18）：uv run pytest -q 全量 360 passed；compose 重建部署 healthz 200；curl 复核列表表头=信源/类型/信源信用/历史反馈、画像页查看态与编辑态短标题齐备；headless 截图 + 视觉复核——画像页 主体/信用/入口/情报 字重一致，条目详情页五个折叠区块（元数据/独立信源计数/转引链/评级历史/反馈记录）与 h2 拉齐、无布局破损。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
列表删「采集入口/状态」两列（表头四列）；画像页查看/编辑态五处标题缩短（信用/入口/情报）；app.css details.box>summary 补 font-weight:700 拉齐 h2（全站折叠区块生效）；tests 三处断言随改。术语表正本不变（界面短标签、文档全称）。
<!-- SECTION:FINAL_SUMMARY:END -->
