---
id: IIH-01
title: 搭建工程骨架、数据库基线与测试CI框架
status: To Do
assignee: []
created_date: '2026-09-10 12:48'
labels:
  - tech
  - ledger
milestone: m-0
dependencies: []
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
奠基（tech enabler，数量封顶 2 之一）：单机单体起架并立测试与 CI 骨架，为后续所有端到端故事提供可运行、可回归的底座。技术架构 §3 选型（FastAPI+SQLAlchemy+Alembic+PostgreSQL+Docker Compose）；最简 schema 落地（数据设计 §1 字段，表名/字段名用术语表 English 列）；pytest + GitHub Actions CI 立起（仓库已在 GitHub，无额外组件，符合组件最少化）。此故事无消费方可见价值，DoD 为工程性验收。关联技术架构 doc-05、数据设计 doc-04。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一个空仓库 When 执行 docker compose up Then web-app 与 postgres 启动且 web-app 连库成功
- [ ] #2 Given Alembic 初始迁移 When 执行 alembic upgrade head Then 建齐最简 schema（情报条目含状态/评级/作废标记/溯源字段、信源、途径、媒介、载体、实体提及、分发记录），命名用术语表 English 列
- [ ] #3 Given 一个 pytest 用例 When 在本地执行 pytest Then 测试框架可运行且通过
- [ ] #4 Given 一次 push 到 main When GitHub Actions 触发 Then CI 跑 pytest 并报告结果
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 术语使用与 backlog/docs/doc-03 - 术语表-Glossary.md 一致，无同义词混用
- [ ] #2 涉及架构决策时已更新 backlog decision
- [ ] #3 影响概念/术语时已同步 backlog/docs/doc-02 - 领域模型-Domain-Model.md
- [ ] #4 智能体产出附依据，无溯源不落账
<!-- DOD:END -->
