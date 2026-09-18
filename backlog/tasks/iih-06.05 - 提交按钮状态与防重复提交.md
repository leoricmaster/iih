---
id: IIH-06.05
title: 提交按钮状态与防重复提交
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-18 03:07'
updated_date: '2026-09-18 03:18'
labels: []
dependencies: []
parent_task_id: IIH-06
type: feature
ordinal: 30002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为日常使用者，我在空表单或必填未填齐时看到提交按钮置灰、提交起动后按钮即时锁定，以避免无效提交与重复落账。

用户使用反馈：录入素材页空表单仍可点「提交」，走服务端往返才报「请上传附件，或填写文字纪要」；转写稿未改动可保存（追加冗余派生记录，「保存并重新抽取」还白白撤回重抽）；发言人实名未填齐可点「完成标记」；新建需求缺必填可点「创建」；全站 POST 表单无防双击——「新建需求」双击会落两条需求（服务端无去重）。且 app.css 无禁用态样式，禁用后外观与可点一致。按业界规范补齐：无效状态禁用提交、必填联动、弹窗焦点首字段、提交起动后锁定按钮。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 提交素材：附件与文字纪要均为空时「提交」置灰，任一有内容即启用
- [x] #2 转写稿编辑：进入编辑后未改动或清空时「保存 / 保存并重新抽取」置灰，改动后方可用
- [x] #3 发言人标记：实名未填齐时「完成标记」置灰
- [x] #4 新建需求：名称或内容规格为空时「创建」置灰，弹窗打开焦点落在名称输入框
- [x] #5 全站 POST 表单提交起动后提交按钮即时禁用；「新建需求」双击仅落一条需求
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. requirements.html：新建需求表单名称 input 加 data-req autofocus、内容规格 textarea 加 data-req。
2. app.js 五块：扩展 dropzone IIFE（附件数 0 且纪要空白时禁用「提交」）；扩展转写稿 tr-edit IIFE（进入编辑记原文，未改动或清空禁用「保存/保存并重新抽取」）；新增 marksform 全部实名非空才启用「完成标记」；新增通用 [data-req] 必填联动（全非空才启用提交按钮）；新增 document 级 POST 表单防双击（setTimeout(0) 禁用提交按钮，保住 submitter name/value——「保存并重新抽取」与快捷反馈依赖）。
3. app.css：补 .btn:disabled 样式（含 hover 抑制、primary 变体）。
4. 验证：uv run pytest tests/test_web.py 回归；起应用手工过五条 AC。
范围外（用户已裁决）：编辑表单（内容规格/采集配置/信源编辑）脏检查不做；「保存并重新抽取」二次确认不做；反馈表单不禁用（空理由合法）。
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
验证（CDP 驱动 headless Chrome 过 UI，本地 uvicorn:8001 + compose Postgres/MinIO）：completed 阶段 8/8——AC#1 空表单置灰/填纪要启用/清空再置灰/加附件启用/移除附件再置灰，AC#2 编辑初开「保存/保存并重新抽取」置灰、改动启用、取消还原再置灰；transcribed 阶段 6/6——AC#2 待标记态三态，AC#3 实名未填齐置灰、填齐启用；reqs 阶段 6/6——AC#4 弹窗焦点在名称框、空/仅名称置灰、齐备启用，AC#5 首击后按钮锁定、双击（间隔 30ms）仅建一条（两轮 DB DELETE 各命中 1 行交叉实证）。回归：uv run pytest tests/test_web.py 87 passed；node --check app.js 通过。测试数据已清理（临时需求删除、素材 1 状态还原 completed）。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
录入素材「提交」、转写稿「保存/保存并重新抽取」、发言人「完成标记」、新建需求「创建」四类提交按钮按空/未填/未改动状态置灰（前端状态、后端校验为准），全站 POST 表单 submit 起动后经 setTimeout(0) 禁用提交按钮防双击（保住 submitter name/value）；补 .btn:disabled 样式与新建需求弹窗 autofocus。改动 3 文件：requirements.html、app.js、app.css。CDP 驱动 headless Chrome 过全部 5 条 AC（20/20 断言），pytest 87 passed。
<!-- SECTION:FINAL_SUMMARY:END -->
