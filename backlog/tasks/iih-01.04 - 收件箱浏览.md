---
id: IIH-01.04
title: 收件箱浏览
status: Done
assignee:
  - '@lancer'
created_date: '2026-09-11 01:40'
updated_date: '2026-09-14 10:07'
labels:
  - product
  - ui
milestone: m-0
dependencies:
  - IIH-01.03
references:
  - doc-07 §3
  - prototype/index.html
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要在收件箱浏览已核实情报，以便日常高效获取情报。

收件箱为首页（doc-07 §3、原型「收件箱/条目详情」页）：列表展示陈述摘要+二维评级+状态；条目详情可看溯源五要素与评级依据。分发匹配与推送后续里程碑加厚。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 存在已核实条目 When 消费方打开收件箱（首页） Then 可见条目列表，每条展示陈述摘要+二维评级+状态（对照原型收件箱页走查）
- [x] #2 Given 消费方点开某条目 When 进入详情 Then 可看溯源五要素与评级依据
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. web/inbox.py 路由：GET /（收件箱=首页，VERIFIED 条目列表）+ GET /items/{id}（条目详情，404 处理） 2. 模板 inbox.html（陈述摘要+二维评级+状态，对照原型收件箱页）/ item_detail.html（溯源五要素 + 评级依据：最近一条 VerificationRecord 的 rationale/N/R/内容可信度/公式版本） 3. app.py 注册路由；既有两页导航补「收件箱」链接 4. test_web.py 增用例：AC#1 列表展示、AC#2 详情五要素+评级依据、空态、404、非已核实不出现 5. 门禁 ruff/mypy/pytest 全绿 + 浏览器走查（对照原型）
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
实现完成：web/inbox.py（GET / 收件箱列表 + GET /items/{id} 详情，404 处理）+ inbox.html / item_detail.html 模板 + app.py 注册路由；既有两页导航补「收件箱」链接（首页可达）。
验证：AC#1 = test_inbox_is_homepage_and_lists_verified_items + 本地起服 curl 走查 /（陈述摘要+B2 二维评级+已核实状态+详情链接）；AC#2 = test_item_detail_shows_provenance_and_rating_basis + 走查 /items/{id}（溯源五要素：载体/媒介/采集时间/原文快照/信源与途径归因；评级依据：rationale+N/R/内容可信度/公式版本）。另测空态、非已核实不出现、404。
门禁：ruff check / ruff format --check / mypy / pytest --cov 全绿（139 passed，web/inbox.py 覆盖 100%，全仓 95%）。
走查数据：本地 iih 库手工插入一条演示用已核实条目（B2 + 转引链节点 + 核实记录，item id=2），供浏览器走查；分发匹配与推送为后续里程碑范围（任务描述明示）。

DoD #3 补正：首推 CI 暴露两处积压问题并已修复——(1) 01.02/01.08 迁移文件未过 ruff format（本地门禁漏 alembic 目录，已对齐 CI 口径）；(2) test_cli_review_e2e_no_leads_skips 漏 stub make_llm_client，无凭证环境构造真实客户端报错（已补 stub）。修复提交 a65cacf + 414fa8d 推送后 CI 全量绿（139 passed，ruff/format/mypy/pytest-cov --cov-fail-under=80），DoD #3 以 GitHub Actions 运行记录为准。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
实现收件箱浏览（doc-07 §3、原型「收件箱/条目详情」页）：收件箱为首页 GET /，列表展示已核实条目的陈述摘要 + 二维评级 + 状态；条目详情 GET /items/{id} 展示溯源五要素（载体/媒介/采集时间/原文快照/信源与途径归因）与评级依据（最近一条核实记录：rationale、独立信源数 N、信源可靠度 R、内容可信度、公式版本）。分发匹配与推送后续里程碑加厚（任务描述明示）。

交付物：web/inbox.py 路由 + inbox.html / item_detail.html 模板 + app.py 注册 + 既有两页导航补「收件箱」链接；test_web.py 增 4 用例（AC#1 列表、AC#2 详情五要素与评级依据、空态与非已核实过滤、404）。

验证：AC#1/AC#2 均以自动化用例 + 本地服务渲染走查双证据勾选；门禁 ruff check / ruff format --check / mypy / pytest --cov 全绿（139 passed，全仓覆盖 95%，inbox.py 100%）。本地 iih 库含一条演示用已核实条目（B2）供浏览器复核。
<!-- SECTION:FINAL_SUMMARY:END -->
