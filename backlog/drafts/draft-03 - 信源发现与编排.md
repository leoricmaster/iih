---
id: DRAFT-03
title: 信源发现与编排
status: Draft
assignee: []
created_date: '2026-09-15 03:45'
labels:
  - product
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
系统主动发现并引入新信源，多途径、按节奏盯守（doc-01 场景 1 常驻监控的完整形态）。

范围轮廓：
- 池外自由探索：监控池外的话题/信源发现
- 新信源引入：双通道确认制（decision-05），归因新建待确认与消费方确认闭环
- 多途径编排：同一信源多出口（官网/公众号/邮件订阅等）统一编排
- 调度节奏：定时/事件触发；届时加情报需求生效窗口字段、collection_task 落账（doc-06 §2）

现状边界：MVP 为种子信源手动登记 + 手动 collect，单途径、无节奏。

明细约束：故事按端到端能力拆，不按技术层拆（archive 旧层级切片已废弃）；术语从 doc-03。

开放问题：池外探索的判断归哪个智能体（定向加厚）；节奏配置粒度（信源级/需求级）；新媒介类型引入的论证流程（doc-01 关键前提：自部署组件最少化）。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
