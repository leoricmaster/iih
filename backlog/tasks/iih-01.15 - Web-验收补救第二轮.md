---
id: IIH-01.15
title: Web 验收补救第二轮
status: Done
assignee: []
created_date: '2026-09-15 04:04'
updated_date: '2026-09-15 04:57'
labels:
  - product
  - web
  - pipeline
milestone: m-0
dependencies: []
references:
  - doc-06 §3
  - doc-07 §2.2
  - doc-07 §3
  - doc-07 §5
  - doc-04 §1
parent_task_id: IIH-01
type: chore
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
第二轮 Web 验收补救并单（2026-09-15 验收，四项裁决留痕：立即运行移顶栏、表单入口用折叠面板、事件时间本轮补抽取、反馈区按「收件箱一键 / 详情页单表单」重构）。补救点：① 信源库与情报需求页表格支持列宽拖拽（localStorage 记忆）；② 登记信源与新建情报需求收成折叠面板入口（默认收起、校验失败自动展开回显），登记信源表单紧凑化（信源主体→主体、初始信用→初始评级，两行栅格）；③ 情报需求页删「状态 × N」分组标题，单表按状态序（激活→草稿→暂停→关闭）；④ 立即运行移顶栏常驻（全局生产控制动作，任意页可触发，跑完跳回收件箱）；⑤ 采集智能体陈述抽取补事件时间抽取（LLM 自正文提取，无法判定留空）——事件时间为时效口径与过期反馈的判断依据（doc-03 事件时间）；⑥ 已核实详情页评级依据两行并一行；⑦ 条目详情反馈区重构为单表单（类型点选高亮、选事实错误才出必填提示与校验），收件箱保留一键反馈，删常驻提示文字。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 信源库或情报需求页 When 拖拽表头右缘 Then 列宽调整且刷新后保持（localStorage）
- [x] #2 Given 信源库页 When 未点开登记信源 Then 表单不占版面；点开后就地展开两行紧凑表单（主体/类型/初始评级/途径/采集入口）；校验失败自动展开回显错误
- [x] #3 Given 情报需求页 When 查看 Then 无「激活 × N」分组标题，单表按 激活→草稿→暂停→关闭 排序；新建入口为折叠面板
- [x] #4 Given 任意页面 When 点击顶栏「立即运行」Then 跑一轮流水线并跳回收件箱 toast 摘要；收件箱页内不再有运行条
- [x] #5 Given 自动拉取的文章页正文含事件时间 When 采集智能体抽取 Then 条目落账事件时间并在列表与详情展示；正文无时间依据则留空
- [x] #6 Given 已核实条目详情页 When 查看 Then 评级依据仅一行（公式版本：N=.. · R=.. → 可信度 .. → 评级 ..）
- [x] #7 Given 已核实条目详情页 When 反馈 Then 单表单：类型点选高亮，选「事实错误」时理由转必填并出提示，其余可选；收件箱一键反馈保留；常驻提示文字删除
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
白盒计划：
1. 列宽拖拽：新增 static/app.js（原生 JS，th 右缘 mousedown 拖拽 → 设 col 宽 → localStorage 按页面键记忆），base.html 引脚本；信源库/情报需求表格加 data-resize 标记。CSS：表头 resize 光标。
2. 顶栏常驻立即运行：base.html topbar 加 POST /pipeline/run 小按钮（表单）；inbox.html 删 runbar；pipeline.py 完成跳转不变（回首件箱）。
3. 折叠面板入口：sources.html/requirements.html 表单改 <details class="box form-panel">，summary 按钮化（＋ 登记信源 / ＋ 新建情报需求）；有 errors 时 open。sources.py/requirements.py 传 errors 已有，模板加 {{ ' open' if errors }}。
4. 表单紧凑：登记信源改两行栅格（grid2 两行）：主体/类型/初始评级 + 途径/采集入口；标签改名（信源主体→主体、初始信用→初始评级）。
5. 需求页单表：删分组循环，单表按 GROUP_ORDER 排序（requirements.py 排序 or 模板排序），保留状态列。
6. 事件时间抽取：collector.py StatementExtractionResult 加 event_time: date | None（正文可考的时间，无法判定留空），EXTRACTION_SYSTEM_PROMPT 加要求；naive 当 UTC；payload.event_time 传入（state_machine 已映射）。测试同步。
7. 评级依据一行：item_detail.html 53-57 并为单行（公式版本：N · R → 可信度 → 评级），rationale 只留评级历史表。
8. 反馈单表单：item_detail.html 已核实态反馈区改单表单——radio 隐藏 + label chip 样式（复用 .chip），选事实错误时 JS 切 textarea required 与标签提示（app.js 几行）；删快捷按钮行与常驻提示；收件箱 inbox.html 快捷按钮保留。
9. 文档同步：doc-06 §3 抽取输出补事件时间；doc-07 §3 页面结构（顶栏运行、折叠面板）、§5 反馈交互（详情页单表单）。
10. 测试与验收：pytest 全绿；本地起 uvicorn 用 seed 数据人工过一遍七条 AC；push 后 CI 绿再关单。
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
验证证据（2026-09-15）：本地门禁全绿（ruff check/format、mypy、pytest 246 通过、覆盖 92.9%）；CI gate 55s 绿（run 34930686286，commit 3fc9533）。起 8001 实例连真实库过 AC：折叠面板默认收起/错误自动展开（HTTP POST 验证）、需求页单表无分组标题、顶栏运行表单全页在位、收件箱 runbar 已删、评级依据单行渲染、反馈单表单（事实错误空理由被服务端驳回并回显预选、六类型 chip 渲染）。事件时间经单测（naive→UTC 提案与落账）。列宽拖拽与条件必填切换为 app.js 交互（语法经 node --check、脚本就位），拖拽手感以用户浏览器验收为准。既有条目 event_time 为历史空值，新一轮采集起生效。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
七项验收补救全部落地：列宽拖拽、登记/新建折叠面板与表单紧凑化、需求页单表、立即运行移顶栏、采集抽取事件时间、评级依据一行、反馈单表单重构（收件箱一键/详情补理由分工）；本地门禁与 CI 绿，推送 3fc9533。
<!-- SECTION:FINAL_SUMMARY:END -->
