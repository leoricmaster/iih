---
id: decision-07
title: ADR 迁移至 backlog decision
date: '2026-09-07 01:48'
status: 已采纳
---
> 2026-09-07 用户裁决。

## 背景

ADR 原以 `docs/adr/` 手工编号管理（01–06）。标题内嵌序号与工具分配的 ID 双轨，易漂移。

## 决定

- ADR 由 `backlog decision` 管理，迁入 `backlog/decisions/`；原 docs/adr/01–06 对应 decision-01–06，正文原样迁入并附迁入溯源行。
- ID 由工具分配，`zeroPaddedIds = 2` 补零两位；标题不含序号。
- 文件结构与元数据（ID、状态、日期）不手改，走 `backlog` CLI；正文在 CLI 创建的文件内编辑。
- 新决策取代旧决策时，以新 decision 落账并标注旧篇。

## 后果

`docs/adr/` 移除；CLAUDE.md、Definition of Done、docs/domain-model.md 的引用同步更新。
