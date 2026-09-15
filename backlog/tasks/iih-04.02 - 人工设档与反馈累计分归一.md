---
id: IIH-04.02
title: 人工设档与反馈累计分归一
status: To Do
assignee: []
created_date: '2026-09-15 06:14'
labels:
  - product
  - ledger
dependencies: []
references:
  - doc-04 §2.3
  - decision-04
  - IIH-01.06
  - IIH-01.13
parent_task_id: IIH-04
type: feature
ordinal: 17002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方/运维方，我想要人工设的信源信用档与反馈累计分两机制归一，以便人工先验不被反馈覆盖、信用档反映两者共同作用。

现状（m-0 验收发现）：人工设档（登记初始档、画像页改档）直接写 source.credit、不产生信用调整记录；反馈累计分仅由反馈增量重放（自 0 起算），下一次反馈即按累计分回写档位——人工先验被覆盖（验收实测：手工设 B 后一条反馈即回 C）。

范围：裁决两机制归一方案——人工档折算为初始分并入引擎、或两机制分层（人工档为覆盖先验、反馈分仅在无人工档时接管）等方案择一；落账后人工档与反馈累计分共同决定 source.credit，变更可追溯。

范围外：信用公式本身调整（半衰期、分档阈值仍按 doc-04 §2.3）；多消费方信用分歧。

关联：doc-04 §2.3（信源信用公式）、decision-04（信用归因）、IIH-01.06（m-0 反馈驱动信用更新奠基）、IIH-01.13 验收发现的缝隙留痕。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方为信源 S 人工设档 B When 随后消费方给一条有效反馈 Then source.credit 反映人工档与反馈累计分的共同作用（人工档不被反馈覆盖）
- [ ] #2 Given 人工档与反馈累计分任一变更 When 重放信用计算 Then 得同一 source.credit（可重放，变更历史可追溯）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
