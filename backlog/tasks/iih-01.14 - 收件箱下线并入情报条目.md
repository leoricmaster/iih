---
id: IIH-01.14
title: 收件箱下线并入情报条目
status: In Progress
assignee: []
created_date: '2026-09-16 15:02'
updated_date: '2026-09-16 15:33'
labels:
  - product
dependencies: []
references:
  - doc-07 §3
type: chore
ordinal: 22002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
信息架构调整（doc-07 §3 修订）：拆分后收件箱页内只剩「待反馈」一个队列，本质是情报条目的一个筛选视图；且 doc-07 §4 已裁决 IM 推送为唯一分发通道、站内收件箱仅为兜底，页面形态与终局不一致。收件箱页下线：情报条目列表加「反馈」筛选维度（待反馈/已反馈/全部），待反馈 = 已核实 ∧ 未作废 ∧ 无反馈（原收件箱口径）；默认视图待反馈，消费优先不变；待反馈计数徽标迁至情报条目导航项；/ 重定向 /items。反馈入口落条目详情页（一步可达，doc-07 §5）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 情报条目列表可按 待反馈/已反馈/全部 筛选，待反馈口径与原收件箱一致（已核实∧未作废∧无反馈），默认视图为待反馈
- [ ] #2 / 重定向 /items；侧栏无收件箱项；待反馈计数徽标挂在情报条目导航项，口径与筛选一致
- [ ] #3 反馈提交经条目详情页一步可达，落账后默认视图出队（与原收件箱行为一致）
- [ ] #4 列表行内快捷反馈：待反馈条目行 hover 出现「有效/重复噪音」快捷按钮，提交落默认理由并出队、回列表 flash 提示；非待反馈条目不出现
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 doc-07 §2/§3/§4/§5 同步修订（收件箱页下线、首页迁移、反馈入口收敛到详情页）；doc-05 §2 兜底措辞同步
- [ ] #3 本地门禁绿（ruff/mypy/pytest --cov-fail-under=80）+ Docker 重建后逐页核对
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. items.py 加反馈筛选维度（feedback: pending/given/all，pending=已核实∧未作废∧无反馈），默认 pending；模板加筛选行
2. inbox.py 删 inbox_page 与待反馈查询，/ 改重定向 /items；context.py inbox_count → feedback_pending_count，徽标迁情报条目；删 inbox.html
3. doc-07 §2/§3/§4/§5 修订 + doc-05 §2 措辞同步
4. 测试同步：收件箱用例改写为重定向/默认视图/出队/徽标；门禁 + Docker 重建核对
5. 列表行内快捷反馈：items.py 传入待反馈判定（避免逐行 lazy load），items.html 行尾 hover 快捷按钮（有效/重复噪音），app.css hover 展开样式；doc-07 §3/§5 反馈入口措辞同步；测试补行内快捷反馈用例
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
- 情报条目列表加「反馈」筛选维度（待反馈/已反馈/全部）：待反馈 = 已核实 ∧ 未作废 ∧ 无反馈（原收件箱口径），默认视图即待反馈，消费优先不变；检索表单与各行 chip 链接携带全部筛选参数。
- 收件箱页下线：`/` 303 重定向 `/items`；inbox.py 仅存反馈提交与异议重审编排；删 inbox.html；侧栏「消费」组 = 情报条目（挂待反馈徽标 feedback_pending_count）+ 警报（置灰）。
- 流水线入口改落 `/items?flash=`，items 页渲染 flash（运行摘要「已核实 N、存疑 M」明示存疑，结果不消失；存疑另可经状态筛选一步可达）。
- 反馈入口收敛到条目详情页单表单（doc-07 §5）；理由留空走「快捷 · {类型}」默认理由不变。
- 文档：doc-07 §2（跨对象视图仅剩图谱、页面表删收件箱行、情报条目默认视图）、§3（导航与徽标归属）、§4（站内以情报条目列表兜底）、§5（Web 反馈入口仅详情）修订；doc-05 §2 同步兜底措辞。
- 测试：收件箱 5 用例改写（重定向+默认视图 / 非待反馈不入 / 反馈落账出队+徽标归零 / 反馈维度分拣 / 存疑可达），既有筛选用例补 feedback=all 组合；374 passed 覆盖 89.5%；ruff/mypy 绿；Docker 重建后逐页核对（重定向、导航、四行筛选、徽标、详情反馈入口）。

- 【验收补救 · 第 2 轮（2026-09-16，行内快捷反馈并入）】任务号 IIH-06 → IIH-01.14（归 01 系列）。列表行内快捷反馈：待反馈行（已核实 ∧ 未作废 ∧ 无反馈，单查询判定不逐行 lazy load）行尾 hover 展开「有效 / 重复噪音」chip 按钮（visibility 占位防行高跳动，POST 复用 /items/{id}/feedback 按 referer 回列表带 flash，默认理由「快捷 · {类型}」）；非待反馈行不出现。doc-07 §2（核心动作）、§5（第四入口「条目 · Web 列表」）、§6（移动端措辞 + 残留收件箱清理）同步。测试 +2（仅待反馈行出现 / 列表提交落账出队），376 passed 覆盖 89.5%；Docker 重建后元素级核对（表 10 列、CSS 规则、POST 303 回跳）。
<!-- SECTION:FINAL_SUMMARY:END -->
