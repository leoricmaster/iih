---
id: IIH-01.14
title: IIH-01.13 Web 验收补救
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-14 15:52'
updated_date: '2026-09-15 03:27'
labels:
  - product
  - web
milestone: m-0
dependencies: []
references:
  - doc-02 §4.1
  - doc-02 §6
  - doc-07 §5
  - doc-06 §3
  - doc-04
  - doc-05
  - doc-07 §2.2
  - doc-07 §3
parent_task_id: IIH-01
type: chore
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
IIH-01.13 Web 验收补救轮并单（2026-09-15 裁决：一轮验收一张 chore，不按补救点开单）。

原 IIH-01.14 审查异议重审：噪音态条目补审查异议纠偏闭环（doc-02 §4.3、§6，doc-07 §5）。审查异议为反馈第七类型，仅对噪音态条目开放、理由必填（理由为重审输入）。提交后审查智能体携异议理由独立重审（不默认服从原判或异议）：重审通过回候选并即时确定性核实（可出评级）；维持否决留噪音。异议与重审决策均版本化留痕（反馈记录 + ReviewDecision 历史），供迭代通路校准审查口径；条目详情状态迁移轨迹完整呈现重审往返。裁决留痕：验收偏差（2026-09-14）提出「审查否决后无纠偏路径」，经裁决选「异议回流重审」方案；经裁决不作为独立 feature（验收衍生补救归 chore）。

并入原 IIH-01.15 两跳采集与原文快照对象存档：途径入口页按列表页处理，采集智能体先选文章链接、抓取文章页、陈述抽自文章页——原文 URL 即实际抓取地址；入口页即文章页时单跳回退；选链命中已采集 URL 仅追加转引链节点。原文快照改存原始 HTML 至 MinIO（内容寻址键），详情页快照收为应用内链接（沙箱回放）；人工提交路径快照仍为提交文本。

并入原 IIH-01.16 情报需求表单引导：内容规格表单 placeholder 给出示例写法（主题/关注对象/排除项），配合试采集预览形成「填—试—调」闭环；不做结构化字段与 LLM 起草。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一条噪音态条目 When 消费方在详情页提交审查异议（理由必填）Then 异议落账，审查智能体携异议理由重审
- [ ] #2 Given 重审通过 Then 条目回候选并即时核实（信源画像齐备时出评级），轨迹呈现「噪音 → 候选（异议重审通过）→ 已核实」完整往返
- [ ] #3 Given 重审维持否决 Then 条目保持噪音，异议与维持决策均留痕，可再次异议
- [ ] #4 Given 非噪音态条目或理由为空 Then 反馈路由驳回，不触发重审
- [ ] #5 Given 途径入口为列表页 When 运行采集 Then 选文章链接并抓取文章页，陈述抽自文章页，原文 URL 为文章页地址（非入口页）
- [ ] #6 Given 选链命中已采集 URL Then 不重复抓取与抽取，仅追加转引链节点
- [ ] #7 Given 入口页即文章页（选链判空）Then 单跳回退，原文 URL 为入口地址
- [ ] #8 Given 自动拉取条目 Then 原文快照为原始 HTML 存对象存储，详情页呈现快照链接（沙箱回放），默认视图仅陈述/评级/轨迹
- [ ] #9 Given 人工提交条目 Then 快照仍为提交文本（折叠呈现），行为不回归
- [ ] #10 Given 新建情报需求页 When 表单呈现 Then placeholder 示例覆盖主题/关注对象/排除的写法，用户可照示例填写
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 MinIO 服务入 docker compose（含桶初始化），本地重建后端到端走查通过
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
实现计划（已完成）：
1. 记账层：FeedbackType 增 REVIEW_DISPUTE（七类型）；反馈路由分流处置+迭代通路，gating 限噪音态、理由必填；proposal.py 增 ItemReviewDisputePayload/Proposal；state_machine.py 增 _execute_item_review_dispute（Noise→Candidate 或维持，ReviewDecision 留痕，PASS 需激活需求、维持需理由类型）。
2. 判断层：Reviewer.review 增 dispute_note 透传，系统提示词加重审边界（结合异议独立重新判断）。
3. Web 编排：item_feedback 路由对 review_dispute 落账后携理由即时重审（重审失败反馈不丢，错误前缀「异议已记录」）；噪音详情页异议表单（理由必填）；已核实反馈选项排除审查异议；轨迹遍历全部审查与核实记录。
4. 测试：状态机异议（通过/维持/前置/校验）、路由 gating、web e2e（fake LLM 通过→已核实、维持→仍噪音、理由缺失拦截）。门禁：ruff/mypy/pytest-cov≥80。
<!-- SECTION:PLAN:END -->
