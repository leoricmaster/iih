---
id: IIH-02
title: 实现记账层核心：状态机执行器与提案契约
status: To Do
assignee: []
created_date: '2026-09-10 12:49'
labels:
  - tech
  - ledger
milestone: m-0
dependencies:
  - IIH-01
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
奠基（tech enabler，数量封顶 2 之二）：落地记账层唯一写账入口——状态机执行器（技术架构 §4/§5）。接收提案→校验（字段完整、状态前置条件、溯源必填）→执行迁移→写溯源存储，无溯源不落账由校验强制。情报条目状态机（线索→候选→已核实→存疑/否决/噪音，领域模型 §4.3）先落地。此故事无消费方可见价值，DoD 为工程性验收；高可测性——纯逻辑，进 CI 回归。关联领域模型 doc-02 §4.3、技术架构 doc-05 §4/§5。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一个情报条目新建提案（含类型/产出/依据/溯源/公式版本）When 提交状态机执行器 Then 校验通过则执行迁移落账、失败则驳回且状态不变，事务原子
- [ ] #2 Given 溯源字段缺失的提案 When 提交状态机执行器 Then 被驳回，无任何落账（无溯源不落账）
- [ ] #3 Given 一条「线索」态条目 When 收到审查通过提案 Then 状态迁移为「候选」
- [ ] #4 Given 一条「候选」态条目 When 收到核实通过提案 Then 状态迁移为「已核实」
- [ ] #5 Given 上述迁移与校验场景 When 运行 pytest Then 全部通过且进 CI 回归
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
