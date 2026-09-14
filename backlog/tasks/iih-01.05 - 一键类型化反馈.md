---
id: IIH-01.05
title: 一键类型化反馈
status: In Progress
assignee: []
created_date: '2026-09-11 01:41'
updated_date: '2026-09-14 11:07'
labels:
  - product
  - ui
milestone: m-0
dependencies:
  - IIH-01.04
references:
  - doc-02 §6
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要对条目一键给出类型化反馈，以便表达情报质量并驱动系统学习。

反馈入口（doc-07 §5、原型反馈交互）：收件箱或详情页对条目给六类型反馈，一步可达；快捷反馈默认理由「快捷 · {类型}」，Web 可补写，事实错误理由必填（信息架构 §5）；反馈经反馈路由按六类型分流（领域模型 §6）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方在条目卡片 When 一键选择「有效」 Then 反馈落账，默认理由「快捷 · 有效」，路由分流到信用通路
- [ ] #2 Given 消费方在详情页 When 选择「事实错误」但未填理由 Then 校验拦截，必填理由后方可提交
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 模型：FeedbackType 六类型枚举 + Feedback 表（item_id/feedback_type/reason/created_at，doc-04 §1），条目挂 feedbacks 关系；豁免「评价方」（单消费方前提，doc-07 §1，comment 留痕）
2. 反馈路由（记账层新模块 ledger/feedback_router.py，doc-05 §4）：submit 校验（条目存在、事实错误理由必填、空理由默认「快捷 · {类型}」）→ 落账；六类型分流表（doc-02 §6：处置/信用/配置/迭代），信用通路消费归 IIH-01.06
3. Alembic 迁移：feedback 表
4. Web：POST /items/{id}/feedback（成功 303 回来源页，失败渲染详情页带错误）；收件箱行内一键反馈（五类型直发 + 事实错误跳详情补理由）；详情页反馈表单（六类型 + 理由，事实错误必填）+ 反馈记录内联（doc-07 §3）
5. 测试：路由单测（默认理由/事实错误必填拦截/分流表全类型）+ Web 用例（AC#1 一键有效默认理由落账且分流含信用通路；AC#2 事实错误无理由拦截不落账、补理由后可提交；无效类型/404）
6. 本地门禁 ruff/mypy/pytest-cov 对齐 CI 口径，push 后 CI 绿再收尾
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
实现落账：Feedback 表（六类型枚举）+ 反馈路由 ledger/feedback_router.py（submit 校验落账 + FEEDBACK_ROUTING 分流表，doc-02 §6）+ Web 入口（收件箱行内一键五类型直发、事实错误跳详情；详情页六类型表单、事实错误理由必填、反馈记录内联）+ 迁移 c3d4e5f6a7b8。本地门禁全绿：156 用例、覆盖率 94.95%、ruff/mypy/format 通过。
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-09-14 11:01
---
豁免留痕（doc-08 豁免规则）：Feedback 表豁免「评价方」字段——单消费方前提（doc-07 §1），同 IntelligenceRequirement 豁免「提出方」先例；反馈目标本任务仅情报条目，命题反馈待命题实体落地后开放。
---
<!-- COMMENTS:END -->
