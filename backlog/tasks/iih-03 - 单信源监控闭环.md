---
id: IIH-03
title: 单信源监控闭环
status: To Do
assignee: []
created_date: '2026-09-10 12:49'
updated_date: '2026-09-11 03:10'
labels:
  - product
  - pipeline
milestone: m-0
dependencies: []
references:
  - doc-07
  - doc-06 §3/§4/§5
  - doc-02 §4.3/§6
  - decision-04
  - decision-08
  - decision-11
  - prototype/index.html
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方与运维方，我想要对已登记的单个种子信源跑通完整的情报生产与反馈闭环，以便产出可溯源、带二维评级的情报条目供消费方浏览，并通过反馈持续校正信源信用。

范围（价值流）：种子信源登记（信源=发布主体，途径=采集入口，decision-17）→ 素材人工录入产出线索（溯源五要素齐备）→ 审查智能体过滤（通过为候选、否决为噪音）→ 核实智能体评级（二维评级，落「已核实」）→ 收件箱浏览 → 一键类型化反馈 → 信用归因与信源信用更新。每步经状态机执行器提案落账，无溯源不落账。

范围外（后续里程碑加厚）：自动采集、主动推送、分发匹配、事件同一性、实体归一、级联重估传播深度。

非功能需求：落账全程审计可追溯（推理记录含公式版本、信用计算可重放）；单机部署可用；生产链各环节不做时延承诺（人工节奏）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方人工录入一条素材（媒介互联网）When 经审查通过、核实评级 Then 消费方收件箱可见该条带二维评级的已核实情报条目，溯源五要素齐备（端到端验收，对照原型录入页→条目详情→收件箱走查）
- [ ] #2 Given 消费方对一条已核实条目给「有效」反馈 When 反馈路由与信用归因执行 Then 定位责任信源（转引链最早引入者），信用计算器按 decision-04 更新分档，如实转述者不受奖惩
- [ ] #3 Given 消费方给「事实错误」反馈并填理由 When 归因与计算执行 Then 条目打作废标记、责任信源信用扣减落账（级联重估本里程碑验证作废落账即可）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
