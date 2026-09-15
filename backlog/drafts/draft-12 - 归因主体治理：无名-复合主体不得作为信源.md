---
id: DRAFT-12
title: 归因主体治理：无名/复合主体不得作为信源
status: Draft
assignee: []
created_date: '2026-09-15 13:39'
labels:
  - product
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
现象：人工录入归因产生「王总、李总（公司管理层）」这类复合无名待确认信源（见运行库 source 表）。

问题：无明确名字的主体（如会议录音转写稿中的多位发言人合称）不可作为信源——信源按发布主体记账（信用、独立性），复合/无名主体会引起归因模糊与信源池混乱。

应然（方向，待梳理）：
- 归因智能体（doc-06 §2 采集段归因）对无明确主体名的素材不新建信源，宁可留空待人工补充；
- 转写/抽取环节（ASR 管线，doc-04 载体处理）应拆分发言人或标不可归因；
- 存量清理：运行库中既有复合待确认信源如何处置（拒绝留痕 or 人工拆分）。

来源：IIH-05.01 走查时用户反馈，当场裁决不在本单修、留此单跟进。关联 doc-06 智能体规约。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
