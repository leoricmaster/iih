---
id: IIH-08.01
title: CI Actions 运行时升级（node20 → node24）
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-18 02:09'
updated_date: '2026-09-18 02:09'
labels:
  - infra
  - ci
dependencies: []
references:
  - >-
    https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
  - 'https://github.com/orgs/community/discussions/189324'
parent_task_id: IIH-08
priority: medium
type: chore
ordinal: 28002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub 自 2025-09-19 起弃用 Actions 的 Node 20 运行时（Node 20 已于 2026-04 EOL；2026-06-02 起声明 node20 的 action 被强制以 node24 运行并出弃用注记，2026 年秋季从 runner 移除）。ci.yml 三个 action 引用均在 node20 线上，CI 运行已出现弃用注记。

已核实（读各 tag action.yml 的 runs.using）：actions/checkout@v4、astral-sh/setup-uv@v5、actions/upload-artifact@v4 均声明 node20；各 action 切至 node24 的最低版本分别为 checkout v5、setup-uv v7（v6 仍为 node20）、upload-artifact v6（v5.0.0 仍为 node20）。

升级注意：setup-uv 自 v8 起不再发布浮动 major 标签，须钉完整版本；checkout/upload-artifact 新 major 的 breaking 变更仅涉 pull_request_target 等触发场景，本 workflow 仅 push 触发，不受影响。

范围外（2026-09-18 盘点确认非同类欠债，不在本单处理）：docker-compose 中 minio:latest 未钉版、CI 与镜像的 uv 版本漂移、postgres:17 落后一个 major、Python 依赖 minor/patch 更新——如需处理另立子任务挂入 IIH-08。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ci.yml 三个 action 引用（checkout / setup-uv / upload-artifact）均运行于 node24 运行时
- [ ] #2 push main 后 CI 全绿，运行注记不再出现 Node.js 20 弃用警告
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. ci.yml 三处引用升级：actions/checkout@v4→@v7、astral-sh/setup-uv@v5→@v10.0.1（v8 起上游不再发布浮动 major 标签，须钉完整版本）、actions/upload-artifact@v4→@v7；with 块不动（python-version、enable-cache 输入在 v10 仍存在）。
2. YAML 解析校验 + git diff 展示，经用户审核后提交。
3. push main 触发 CI，确认全绿且运行注记无 node20 弃用警告（AC #2）。
<!-- SECTION:PLAN:END -->
