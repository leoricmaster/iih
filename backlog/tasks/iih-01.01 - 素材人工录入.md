---
id: IIH-01.01
title: 素材人工录入
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 08:38'
labels:
  - product
  - ui
dependencies: []
references:
  - doc-07 §2.3
  - doc-06 §3
  - doc-05 §4/§5/§8
  - prototype/index.html
parent_task_id: IIH-01
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要录入素材产出线索，以便把线下拿到的情报送进流水线。

录入素材页（doc-07 §2.3、原型「录入素材」页）：选媒介、填陈述内容（或上传附件由载体管线最简处理），提交生成线索提案，经状态机执行器落账为「线索」态，溯源五要素齐备。信源与途径不经登记、由采集智能体从素材归因补记（非互联网途径不经登记，doc-06 §3）；识别出未登记信源则经双通道确认制准入（decision-05）。

本故事承载奠基工作包：提案契约与状态机执行器、工程骨架与 CI 基线（选型见技术架构 §1/§3、质量保障见 §8），实现计划于开发启动时编写。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方打开录入素材页 When 选媒介「会议讨论」、填写陈述「W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产」、提交 Then 生成线索提案，落账为「线索」态；信源（W 公司）与途径（渠道大会现场）由采集智能体归因补记（非互联网途径不经登记，doc-06 §3），溯源五要素齐备（载体+媒介+采集时间+原文快照+信源/途径归因）（对照原型录入素材页走查）
- [ ] #2 Given 运维方录入时必填字段缺失 When 提交 Then 表单校验拦截，不生成提案
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
开发启动时编写。
<!-- SECTION:PLAN:END -->
