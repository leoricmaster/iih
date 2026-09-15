---
id: DRAFT-09
title: 需求级采集配置与反馈学习通路
status: To Do
assignee: []
created_date: '2026-09-15 07:46'
labels:
  - product
  - pipeline
dependencies: []
references:
  - doc-04 §1
  - doc-02 §6
  - IIH-01
  - IIH-01.13
priority: medium
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要为每个情报需求独立配置采集频率、时效与来源绑定，以便按需求紧迫度差异化计量、控制负载与费用，并通过「过期」反馈调整配置。

范围：
1. 模型字段：IntelligenceRequirement 加生效窗口（可空=常驻）、采集频率（可空=继承全局 pipeline_interval）、需求-信源绑定（可空=全部已确认互联网途径）。
2. 调度器：按需求独立分发采集任务（频率、来源均独立），取代当前全局间隔 × 全激活需求共用模式。
3. 「过期」反馈学习通路落地（doc-02 §6）：过期反馈触发该需求采集频率/时效参数调整提案落账，非仅路由去向记录。

范围外：池外自由探索、多途径编排优化、调度成本核算仪表盘。

关联：doc-04 §1（情报需求字段含生效窗口）、doc-02 §6（过期 → 采集频率/时效参数）、IIH-01 范围外明列「调度节奏」、IIH-01.13 路径 A 仅 UI 聚合呈现（本单为字段+调度+学习通路完整落地）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方为需求 A 配置频率 1h、需求 B 频率 24h When 调度器运行 Then A、B 按各自频率独立采集，LLM 调用与抓取量按需求分别计量可见
- [ ] #2 Given 消费方对需求 A 的某条目给「过期」反馈 When 学习通路执行 Then 需求 A 的采集频率/时效参数调整提案落账，下轮采集按新参数执行
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
