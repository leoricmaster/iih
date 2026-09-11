---
id: IIH-04.01
title: 作为消费方，我想要在收件箱浏览已核实情报，以便日常高效获取情报
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - ui
dependencies:
  - IIH-03
parent_task_id: IIH-04
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 2 消费反馈链的入口 US（doc-07 §3 收件箱为首页）：收件箱展示已核实条目列表（陈述摘要+二维评级+状态），条目详情可看溯源五要素与评级。消费动线的起点。本里程碑最简展示，分发匹配/推送在后续里程碑加厚。关联信息架构 doc-07 §3。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 存在已核实条目 When 消费方打开收件箱（首页） Then 可见条目列表，每条展示陈述摘要+二维评级+状态
- [ ] #2 Given 消费方点开某条目 When 进入详情 Then 可看溯源五要素与评级依据
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
