---
id: DRAFT-06
title: 人工设档与反馈累计分归一
status: Draft
assignee: []
created_date: '2026-09-15 06:14'
labels: []
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
信源信用两个机制并存的缝隙（doc-04 §2.3）：人工设档（登记初始档、画像页改档）直接写 source.credit，不产生信用调整记录；反馈累计分仅由反馈增量重放（自 0 起算），下一次反馈即按累计分回写档位——人工先验被覆盖（验收实测：手工设 B 后一条反馈即回 C）。

待裁决：人工档折算为初始分并入引擎；或两机制分层（人工档为覆盖先验、反馈分仅在无人工档时接管）等方案择一。

来源：MVP 验收发现（IIH-01.13，2026-09-15），m-0 不动。涉及 doc-04 §2.3、decision-04。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
