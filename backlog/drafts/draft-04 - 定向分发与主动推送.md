---
id: DRAFT-04
title: 定向分发与主动推送
status: Draft
assignee: []
created_date: '2026-09-15 03:45'
labels:
  - product
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
核实后的情报按需求匹配送达消费方，高价值情报主动推送、可一键反馈（doc-01 场景 1 后半）。

范围轮廓：
- 分发匹配：已核实条目按激活情报需求匹配，收件箱定向呈现（分发检索）
- 主动推送：推送通道开通，按评级/信用阈值送达，送达记录落账
- 推送内一键反馈：快捷·{类型}为默认理由，事实错误必填（doc-02 §5）
- 分发记录（送达/反馈）度量需求覆盖，缓解"采而不用"（doc-01 §8）

现状边界：MVP 收件箱为全量浏览，无匹配无推送（Web 已留"推送通道开通后可配"占位）。

明细约束：故事按端到端能力拆，不按技术层拆（archive 旧层级切片已废弃）；术语从 doc-03。

开放问题：推送通道选型（邮件/IM）；匹配判断归智能体还是确定性规则。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
