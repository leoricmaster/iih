---
id: IIH-01.14
title: 审查异议重审
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-14 15:52'
updated_date: '2026-09-14 15:52'
labels:
  - product
  - web
milestone: m-0
dependencies: []
references:
  - doc-02 §4.1
  - doc-02 §6
  - doc-07 §5
parent_task_id: IIH-01
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要对审查否决的条目提交审查异议并触发携理由重审，以便纠正错误否决并持续校准审查智能体。

审查异议（doc-02 §4.3、§6，doc-07 §5）：反馈第七类型，仅对噪音态条目开放、理由必填（理由为重审输入）。提交后审查智能体携异议理由独立重审（不默认服从原判或异议）：重审通过回候选并即时确定性核实（可出评级）；维持否决留噪音。异议与重审决策均版本化留痕（反馈记录 + ReviewDecision 历史），供迭代通路校准审查口径；条目详情状态迁移轨迹完整呈现重审往返。

裁决留痕：用户验收偏差（2026-09-14）提出「审查否决后无纠偏路径」，经裁决选「异议回流重审」方案。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条噪音态条目 When 消费方在详情页提交审查异议（理由必填）Then 异议落账，审查智能体携异议理由重审
- [ ] #2 Given 重审通过 Then 条目回候选并即时核实（信源画像齐备时出评级），轨迹呈现「噪音 → 候选（异议重审通过）→ 已核实」完整往返
- [ ] #3 Given 重审维持否决 Then 条目保持噪音，异议与维持决策均留痕，可再次异议
- [ ] #4 Given 非噪音态条目或理由为空 Then 反馈路由驳回，不触发重审
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
实现计划（已完成）：
1. 记账层：FeedbackType 增 REVIEW_DISPUTE（七类型）；反馈路由分流处置+迭代通路，gating 限噪音态、理由必填；proposal.py 增 ItemReviewDisputePayload/Proposal；state_machine.py 增 _execute_item_review_dispute（Noise→Candidate 或维持，ReviewDecision 留痕，PASS 需激活需求、维持需理由类型）。
2. 判断层：Reviewer.review 增 dispute_note 透传，系统提示词加重审边界（结合异议独立重新判断）。
3. Web 编排：item_feedback 路由对 review_dispute 落账后携理由即时重审（重审失败反馈不丢，错误前缀「异议已记录」）；噪音详情页异议表单（理由必填）；已核实反馈选项排除审查异议；轨迹遍历全部审查与核实记录。
4. 测试：状态机异议（通过/维持/前置/校验）、路由 gating、web e2e（fake LLM 通过→已核实、维持→仍噪音、理由缺失拦截）。门禁：ruff/mypy/pytest-cov≥80。
<!-- SECTION:PLAN:END -->
