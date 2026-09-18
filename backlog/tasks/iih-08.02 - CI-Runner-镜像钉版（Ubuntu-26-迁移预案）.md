---
id: IIH-08.02
title: CI Runner 镜像钉版（Ubuntu 26 迁移预案）
status: To Do
assignee: []
created_date: '2026-09-18 02:29'
labels:
  - infra
  - ci
dependencies: []
references:
  - 'https://github.com/actions/runner-images/issues/14748'
parent_task_id: IIH-08
priority: low
type: chore
ordinal: 29002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub 公告：ubuntu-latest 标签将于 2026-10-19 起自动迁移至 Ubuntu 26 runner 镜像（IIH-08.01 收尾时 CI 注记中发现的到期事项）。届时运行环境自动变更，本项目对 OS 依赖轻（postgres service 容器 + uv 工具链），风险低但非零。

预案二选一：钉 ubuntu-24.04 保持运行环境确定性；或迁移日前用 ubuntu-26 预览标签实跑一轮 CI 验证后随迁。裁决后实施。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 runner 标签策略落定（钉版或验证随迁）并实施，CI 全绿
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
