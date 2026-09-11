---
id: IIH-01.01
title: 素材人工录入
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 03:12'
labels:
  - product
  - ui
dependencies:
  - IIH-01.07
references:
  - doc-07 §2.3
  - doc-06 §3
  - doc-05 §4/§5/§8
  - prototype/index.html
parent_task_id: IIH-01
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要人工录入素材产出线索，以便把线下拿到的情报送进流水线。

录入页（doc-07 §2.3、原型「录入」页）：选信源引用与媒介、填陈述内容（或上传附件由载体管线最简处理），提交生成线索提案，经状态机执行器落账为「线索」态，溯源五要素齐备。

本故事承载奠基工作包：提案契约与状态机执行器、工程骨架与 CI 基线（选型见技术架构 §1/§3、质量保障见 §8），实现计划于开发启动时编写。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方打开录入页 When 选择信源「W 公司 · 官网」与媒介「互联网」、填写陈述「W与Z拟合资」、提交 Then 生成线索提案，溯源五要素齐备（信源引用+载体+媒介+采集时间+原文快照/链接），落账为「线索」态（对照原型录入页走查）
- [ ] #2 Given 运维方录入时必填字段缺失 When 提交 Then 表单校验拦截，不生成提案
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
开发启动时编写。
<!-- SECTION:PLAN:END -->
