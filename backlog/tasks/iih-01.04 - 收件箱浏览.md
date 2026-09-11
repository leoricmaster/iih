---
id: IIH-01.04
title: 收件箱浏览
status: To Do
assignee: []
created_date: '2026-09-11 01:40'
updated_date: '2026-09-11 03:11'
labels:
  - product
  - ui
dependencies:
  - IIH-01.03
references:
  - doc-07 §3
  - prototype/index.html
parent_task_id: IIH-01
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要在收件箱浏览已核实情报，以便日常高效获取情报。

收件箱为首页（doc-07 §3、原型「收件箱/条目详情」页）：列表展示陈述摘要+二维评级+状态；条目详情可看溯源五要素与评级依据。分发匹配与推送后续里程碑加厚。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 存在已核实条目 When 消费方打开收件箱（首页） Then 可见条目列表，每条展示陈述摘要+二维评级+状态（对照原型收件箱页走查）
- [ ] #2 Given 消费方点开某条目 When 进入详情 Then 可看溯源五要素与评级依据
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
