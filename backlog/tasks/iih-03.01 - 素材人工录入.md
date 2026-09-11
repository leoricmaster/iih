---
id: IIH-03.01
title: 素材人工录入
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 01:39'
labels:
  - product
  - ui
dependencies:
  - IIH-01
parent_task_id: IIH-03
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要人工录入素材产出线索，以便把线下拿到的情报送进流水线。

录入页（doc-07 §2.3、原型「录入」页）：选媒介、填陈述内容（或上传附件由载体管线最简处理），提交生成线索提案，经状态机执行器落账为「线索」态，溯源五要素齐备。本故事承载奠基工作包：提案契约与状态机执行器（见 plan，源自原 IIH-02）。关联 doc-06 §3、doc-05 §4/§5。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方打开录入页 When 选择媒介「互联网」、填写陈述「W与Z拟合资」、提交 Then 生成线索提案，溯源五要素齐备（信源引用+载体+媒介+采集时间+原文快照/链接），落账为「线索」态（对照原型录入页走查）
- [ ] #2 Given 运维方录入时必填字段缺失 When 提交 Then 表单校验拦截，不生成提案
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 奠基工作包：提案契约与状态机执行器（记账层唯一写账入口，技术架构 §4/§5）——接收提案 → 校验（字段完整、状态前置条件、溯源必填）→ 执行迁移 → 写溯源存储；先落地情报条目状态机（线索→候选→已核实→存疑/否决/噪音，领域模型 §4.3）
2. 执行器 pytest 用例（源自原 IIH-02 验收）：完整提案迁移落账/缺字段驳回且状态不变（事务原子）；溯源缺失驳回、无任何落账（无溯源不落账）；线索+审查通过提案→候选；候选+核实通过提案→已核实
3. 录入页：选媒介、填陈述、上传附件（载体管线最简）；提交生成线索提案走执行器
4. 表单必填校验：缺失拦截，不生成提案
<!-- SECTION:PLAN:END -->
