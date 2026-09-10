---
id: IIH-03.01
title: 作为运维方，我想要人工录入素材产出线索，以便把线下拿到的情报送进流水线
status: To Do
assignee: []
created_date: '2026-09-10 12:50'
labels:
  - product
  - ui
dependencies:
  - IIH-02
parent_task_id: IIH-03
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature 1 生产链的入口 US（doc-07 §2.3 人工录入）：运维方在 Web 录入页选媒介、填陈述内容（或上传附件由载体管线处理），提交后生成线索提案，经状态机执行器落账为「线索」态、溯源五要素齐备。这是把人工素材变成系统可处理对象的第一步。关联智能体规约 doc-06 §3。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方打开录入页 When 选择媒介「互联网」、填写陈述「W与Z拟合资」、提交 Then 生成线索提案，溯源五要素齐备（信源引用+载体+媒介+采集时间+原文快照/链接），落账为「线索」态
- [ ] #2 Given 运维方录入时必填字段缺失 When 提交 Then 表单校验拦截，不生成提案
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
