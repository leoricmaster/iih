---
id: decision-08
title: 采集任务不落账（暂）
date: '2026-09-14 08:18'
status: 已采纳
---

## Context

IIH-01.08 自动拉取链需要一个"派单"环节：按激活情报需求向已登记互联网途径产出采集任务。问题：采集任务是否需要落账（建 `collection_task` 表）？

落账的代价：建表 + 迁移 + 状态字段 + 消费方查询接口；但目前无持久化消费方——调度节奏（定时/事件触发）属后续任务范围，本任务内 Director 产出任务后立即被 CLI 消费，无中间存储需求。

## Decision

**采集任务不落账**：Director 产出内存 `CollectionTask` dataclass，CLI 即时消费，不持久化。

审计信息（哪条 IR 触发、拉取哪个途径、何时）记入下游产物的 `IntelligenceItemNewProposal.rationale` 与 `IntelligenceItem` 字段（`original_url`、`collected_at`、`source`、`outlet`）已够追溯。

## Consequences

- 当前范围：Director 是纯查询、无状态、不调 LLM 的判断层薄壳；无需新建 `collection_task` 表与迁移。
- 去重依靠既有 `intelligence_item.original_url` + `intelligence_item.content_fingerprint` + `provenance_chain_node.original_url`，无需任务表。
- 后续若引入调度节奏（定时拉取、失败重试、消费方审计），再建持久化任务表并回填此决策的撤销路径。
