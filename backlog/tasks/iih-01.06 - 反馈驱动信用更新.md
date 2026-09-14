---
id: IIH-01.06
title: 反馈驱动信用更新
status: Done
assignee:
  - '@lancer'
created_date: '2026-09-11 01:41'
updated_date: '2026-09-14 11:56'
labels:
  - product
  - ledger
milestone: m-0
dependencies:
  - IIH-01.05
references:
  - decision-04
  - doc-02 §6
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要反馈自动驱动信源信用更新，以便系统越用越准。

有效/事实错误反馈经信用归因（decision-04）定位责任信源——转引链上最早引入该陈述的信源，如实转述者不受奖惩；信用计算器按信源信用公式（数据设计 §2.3）更新信源信用分档。事实错误触发条目作废标记（级联重估传播深度本里程碑验证作废落账即可，后续加厚）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 消费方对一条条目给「有效」反馈 When 信用归因执行 Then 定位到转引链最早引入该陈述的信源，信用计算器按信源信用公式（数据设计 §2.3）+1 并更新分档，如实转载者不动
- [x] #2 Given 消费方对一条条目给「事实错误」反馈 When 归因与计算执行 Then 责任信源 −2、条目打作废标记落账
- [x] #3 Given 同一反馈历史 When 重放信用计算 Then 得同一信用值（可重放）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 信用计算器 ledger/credit.py：公式版本 source_credit_v1；有效 +1 / 事实错误 −2；180 天半衰期累计分 score(t)=Σ delta·2^(-(t-t_i)/180d)；分档阈值映射 A–F（实现时定，定档写入公式注释）。
2. CreditAdjustment 表（信用调整记录）：source_id + feedback_id(唯一) + delta + score_after + grade_after + created_at；alembic 迁移。
3. 信用归因（记账层确定性查找）：转引链 collected_at 最早节点（并列取最小 id）的信源 = 责任信源；待确认信源不参与信用记账（decision-05），反馈照常落账、信用通路跳过。
4. FeedbackRouter.submit 内联信用通路：CREDIT 通路 → 归因 + CreditAdjustment 落账（记 score/grade 快照）+ 更新 Source.credit；FACTUAL_ERROR 处置通路 → item.retracted=True（级联重估后续加厚）；同事务原子提交。
5. 用例：归因命中最早节点/如实转载者不动/待确认信源跳过；+1 与 −2 分档更新；作废落账；同反馈历史重放得同信用值。
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
实现落账：ledger/credit.py（信用计算器 + 确定性归因）+ CreditAdjustment 表（迁移 e4d5f6a7b8c9）+ FeedbackRouter 信用/处置通路内联 + doc-04 §2.3 阈值回填；新增 tests/test_credit.py（公式/归因/AC#1-#3 用例），全量 176 通过 + ruff/format 绿。

验证：CI run 34840632979 全绿（ruff check/format、mypy、pytest-cov 95.25% ≥80%、176 用例）；AC#1-#3 分别由 test_valid_feedback_updates_credit_and_leaves_requoter_untouched / test_factual_error_penalty_and_retraction / test_replay_from_history_reproduces_credit 覆盖。
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: @lancer
created: 2026-09-14 11:53
---
分档阈值裁决（doc-04 §2.3 留「实现时定」）：用户选宽容制 A≥8 / B≥4 / C≥0 / D≥-4 / E≥-8 / F<-8——首个有效反馈落 C、单次事实错误落 D；已回填 doc-04 §2.3。另：decision-04 称归因判断属判断层经提案落档，本里程碑归因规则为确定性查找（转引链 collected_at 最早节点），故作记账层确定性实现、归因结果经 CreditAdjustment 落档可追溯，未引入智能体提案——留痕说明。
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
反馈驱动信用更新落账：ledger/credit.py 信用计算器（source_credit_v1：有效+1/事实错误−2、180 天半衰期、宽容制 A–F 分档——阈值经用户裁決回填 doc-04 §2.3）+ 确定性信用归因（转引链最早引入信源，待确认信源跳过）+ CreditAdjustment 表（快照可重放）+ FeedbackRouter 信用/处置通路事务内联（事实错误同事务打 retracted）。验证：CI 34840632979 全绿（mypy、ruff、pytest-cov 95.25%、176 用例含 AC 三用例）。
<!-- SECTION:FINAL_SUMMARY:END -->
