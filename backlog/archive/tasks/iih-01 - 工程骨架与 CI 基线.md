---
id: IIH-01
title: 工程骨架与 CI 基线
status: To Do
assignee: []
created_date: '2026-09-10 12:48'
updated_date: '2026-09-11 01:38'
labels:
  - tech
  - ledger
milestone: m-0
dependencies: []
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
奠基（tech enabler，MVP 唯一技术故事）：单机单体起架并立测试与 CI 底座，为全部端到端故事提供可运行、可回归的工程基础。技术架构 §3 选型（FastAPI+SQLAlchemy+Alembic+PostgreSQL+Docker Compose）；最简 schema 落地（数据设计 §1，表名字段名用术语表 English 列）；质量门禁进 CI：ruff check、ruff format --check、mypy（基础档）、pytest-cov（--cov-fail-under=80，全仓口径起步，见 doc-08 口径说明）。此故事无消费方可见价值，验收为工程性。关联 doc-05 §3、doc-04 §1、doc-08。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 一个空仓库 When 执行 docker compose up Then web-app 与 postgres 启动且 web-app 连库成功
- [ ] #2 Given Alembic 初始迁移 When 执行 alembic upgrade head Then 建齐最简 schema（情报条目含状态/评级/作废标记/溯源字段、信源、途径、媒介、载体、实体提及、分发记录），命名用术语表 English 列
- [ ] #3 Given 一个 pytest 用例 When 本地执行 pytest --cov Then 测试框架可运行且通过，覆盖率报告生成
- [ ] #4 Given 一次 push 到 main When GitHub Actions 触发 Then CI 依次执行 ruff check、ruff format --check、mypy、pytest --cov（--cov-fail-under=80），任一失败即 CI 红
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
