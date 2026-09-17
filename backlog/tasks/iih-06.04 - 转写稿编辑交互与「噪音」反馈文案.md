---
id: IIH-06.04
title: 转写稿编辑交互与「噪音」反馈文案
status: In Progress
assignee: []
created_date: '2026-09-17 15:15'
labels:
  - product
dependencies: []
references:
  - prototype/index.html
  - doc-03 §190
  - doc-02 §6
  - doc-07 §88
parent_task_id: IIH-06
type: feature
ordinal: 24002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为素材录入者，我打开待标记素材时先看到转写稿全文、可就地编辑保存，再对照完成发言人标记，以便不在嵌套折叠与只读框间来回切换；作为反馈者，我在条目列表可一键把无价值条目标为「噪音」。

本任务整合（原型 prototype/index.html 已评审定稿）：
①待标记态重组：转写稿与发言人标记平级 details 且默认展开，转写稿在前（上下文在前、操作在后）。
②转写稿 view/edit 双态：默认只读 +「编辑」进入编辑，取消还原，保存走表单 POST；已完成态提供「保存并重新抽取」（替代 respecify 勾选框，按钮 name/value 提交，后端行为不变）。
③「标记并抽取」改「完成标记」：标记是人工归因，抽取随后自动，两动作不并列。
④反馈类型「重复 / 噪音」合并为「噪音」：完全重复几乎不发生且重复从属噪音（doc-02 §174：噪音限同源纯重复，跨信源同事件是印证）；术语表 English 列 Duplicate-Noise→Noise，枚举 DUPLICATE_NOISE→NOISE（存值 noise）+ 存量数据迁移。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 待标记素材展示：转写稿在前、发言人标记在后，两块默认展开；编辑可进入/取消/保存，取消还原未保存改动
- [ ] #2 已完成素材转写稿编辑提供 保存 / 保存并重新抽取，后者撤回旧线索并重抽（原 respecify 行为不变）
- [ ] #3 「完成标记」完成人工归因后进入抽取（原标记行为不变）
- [ ] #4 条目列表快捷反馈显示「噪音」，反馈落账类型 noise；术语表/doc-02/doc-07 同步，全库无「重复 / 噪音」残留
- [ ] #5 存量 feedback 数据迁移 duplicate_noise→noise，alembic upgrade/downgrade 可逆
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
