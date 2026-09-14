---
id: IIH-01.08
title: 互联网信源自动拉取
status: Done
assignee:
  - '@lancer'
created_date: '2026-09-11 08:38'
updated_date: '2026-09-14 08:22'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-01.07
references:
  - doc-06 §2/§3
  - doc-07 §2.2
parent_task_id: IIH-01
priority: high
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要系统自动拉取已登记互联网信源的内容产出线索，以便日常省去人工盯信源的人力——监控闭环的核心价值点。

自动拉取链（doc-06 §2 定向、§3 采集、doc-07 §2.2 常驻监控）：定向智能体最简版按激活情报需求向已登记互联网途径派单 → fetcher 拉单页 → 采集智能体识别陈述、组装线索（溯源五要素齐备——信源=登记主体、途径=登记互联网途径）、执行前置指纹去重。与人工录入（IIH-01.01）产出的线索汇入同一审查入口。

范围外（后续里程碑加厚）：调度节奏（定时/事件触发）、池外自由探索、多途径编排、载体管线除网页外的解析。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 已登记信源 W 公司 · 官网（互联网途径，IIH-01.07）且情报需求已激活 When 系统自动拉取该信源 Then 产出线索提案（陈述、溯源五要素齐备——信源 W 公司、途径 官网·互联网、采集时间、原文链接、载体 网页），落账为「线索」态，进入审查
- [x] #2 Given 拉取到与既有条目内容指纹相同的素材 When 采集前置过滤比对 Then 命中不进采集智能体，仅在既有条目转引链追加该信源引用
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 数据模型与迁移：IntelligenceRequirement/ProvenanceChainNode + IntelligenceItem.content_fingerprint/original_url
2. 提案契约扩展：IR register/activate + ItemProvenanceAppend + payload 扩展
3. 状态机扩展：三个 _execute_* 方法 + AUTOMATED 模式 source 必须 confirmed
4. 工具层：fetcher(httpx) + html_normalize(BS4) + 依赖
5. Director：扫激活 IR × 已确认互联网途径，产出内存 CollectionTask
6. Collector 扩展：collect_outlet 前置指纹去重 + LLM 抽取陈述
7. CLI：ir-create/ir-activate/collect 三子命令
8. 端到端验收：docker compose 重建 + 真实 LLM 走查 AC#1/#2
9. 收尾：notes/summary/AC/DoD 勾选 + decision-08「采集任务不落账」
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
阶段 A 完成：models.py 加 IntelligenceRequirementStatus（DRAFT/ACTIVE/PAUSED/CLOSED）+ IntelligenceRequirement 模型 + ProvenanceChainNode 模型（含同(item,source,outlet)唯一约束）；IntelligenceItem 加 content_fingerprint（String(64), nullable, 部分唯一索引 WHERE content_fingerprint IS NOT NULL）+ original_url（Text, nullable）+ provenance_nodes 关系。迁移 f7a2c91b3e4d_ir_provenance_chain.py（down_revision=dbd4fff9cbbd）。test_schema 加 IR + ProvenanceChainNode roundtrip 用例。

阶段 B 完成：proposal.py 加 IntelligenceRequirementRegisterProposal（[*]→Draft）/ IntelligenceRequirementActivateProposal（Draft→Active）/ ItemProvenanceAppendProposal（指纹命中追加节点）三类新提案；IntelligenceItemNewPayload 加可选 content_fingerprint + original_url（仅 AUTOMATED 模式填）。

阶段 C 完成（TDD）：state_machine.py execute() match 加三类新分支；_execute_item_new 写入 content_fingerprint + original_url；AUTOMATED 模式拆 _resolve_confirmed_source（必须 confirmed=True）+ _resolve_existing_outlet（必须已登记），区别于 MANUAL 模式的 _resolve_source/_resolve_outlet（归因新建待确认）；新增 _execute_ir_register / _execute_ir_activate（Draft→Active 前置校验）/ _execute_item_provenance_append（节点不重复校验）。test_state_machine 加 14 用例（IR 登记/激活/前置违反、AUTOMATED 模式边界、节点追加/重复驳回）。

阶段 D 完成（TDD）：tools/fetcher.py（httpx GET 单页，raise_for_status 转 FetcherError）+ tools/html_normalize.py（BS4 剥离 script/style/nav/footer/header + 空白折叠 + SHA-256 指纹）；pyproject.toml 加运行时依赖 httpx>=0.28 + beautifulsoup4>=4.12。test_fetcher 4 用例（200/404/timeout/connection error，mock httpx.Client）；test_html_normalize 7 用例（剥离噪声/空白折叠/指纹确定性）。

阶段 E 完成（TDD）：agents/director.py 新建——CollectionTask frozen dataclass（含 source_type 字段）+ Director.propose_tasks() 扫激活 IR × 已确认信源的互联网途径笛卡尔积，纯查询不调 LLM 不落账（decision-08）。test_director 7 用例（笛卡尔积/状态过滤/confirmed 过滤/internet 过滤/entry 为空/空列表）。

阶段 F 完成（TDD）：agents/collector.py 加 EXTRACTION_SYSTEM_PROMPT + StatementExtractionResult instructor schema + collect_outlet 方法——前置指纹去重（命中 IntelligenceItem.content_fingerprint 追加 ItemProvenanceAppendProposal 不调 LLM）/ 未命中调 LLM 抽取陈述（空陈述返回 None 但计量已发生）/ 非空组装 IntelligenceItemNewProposal（mode=AUTOMATED, modality=webpage, medium=internet, original_snapshot=归一化文本, content_fingerprint=fp, original_url=task.url）。conftest 加 make_fake_llm_extraction + w_extraction fixture。test_collector 加 3 用例（去重命中/未命中/空陈述）。

阶段 G 完成（TDD）：cli/ 新建——__init__.py argparse 入口 + ir.py（ir-create/ir-activate 子命令）+ collect.py（Director→fetcher→Collector→executor 链路，每条独立事务，FetcherError 捕获并日志继续）。test_cli 6 用例（3 端到端 e2e + argparse 校验 + 等价路径），通过 monkeypatch + fake_factory 注入 db_session 提升覆盖率。

阶段 H 完成：本地门禁全绿（ruff check All checks passed、ruff format --check 干净、mypy 22 files no issues、pytest 71 passed coverage 95%）。干净环境 docker compose down -v → up --build → 迁移自动跑 → Uvicorn running on http://0.0.0.0:8000。AC#1 端到端等价路径走查（test_ir_create_then_activate_then_collect_produces_lead）通过：登记 Draft → 激活 Active → Director 派单 → mock fetcher 返回 HTML → Collector 抽取陈述 → 落账 Lead，溯源五要素齐备（modality=webpage, medium=internet, source=W 公司 confirmed=True, outlet=官网, original_url=https://w-mining.example/news, content_fingerprint 非空 64 位）。AC#2 端到端等价路径走查（test_collect_with_duplicate_content_appends_provenance_node）通过：第二次拉取同内容 → 指纹命中 → 追加 ProvenanceChainNode（行业媒体 A），不新建条目、不调 LLM。真实 LLM 走查需 LLM_API_KEY 且非阻塞——mock 测试已覆盖 AC 验证，按 doc-08 豁免规则留痕。

阶段 I 完成：commit 8087b03 推送 main；decision-08「采集任务不落账（暂）」落档；AC#1/AC#2/DoD#1 勾选；情报需求豁免「提出方/生效窗口」在 comment 留痕。
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: @lancer
created: 2026-09-14 08:22
---
豁免痕（doc-08 通用 DoD 豁免规则）：

1. 情报需求模型豁免「提出方」字段——本阶段单消费方前提（doc-07 §1），无多消费方协调需求；后续多消费方引入时回填此字段。
2. 情报需求模型豁免「生效窗口」字段——调度节奏（定时/事件触发）属后续任务范围，本任务 Director 即时消费不依赖时间窗口；调度到来时再加 effective_from/effective_to 字段。
3. 真实 LLM 走查豁免——需 LLM_API_KEY 且非阻塞；mock 测试（fake_llm 替身 + 端到端等价路径）已覆盖 AC#1/#2 验证；后续接入真实 DeepSeek API 时补端到端走查记录。

decision-08「采集任务不落账（暂）」：Director 产出内存 CollectionTask dataclass 即时消费，不持久化；审计信息记入下游 IntelligenceItem 字段（original_url/collected_at/source/outlet）已够追溯；后续调度节奏引入时再建 collection_task 表。
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
实现：数据模型扩展（IntelligenceRequirement 草稿/激活/暂停/关闭状态机 + ProvenanceChainNode 转引链独立表 + IntelligenceItem.content_fingerprint/original_url）→ 提案契约扩展（IRRegister/IRActivate/ItemProvenanceAppend 三类新提案 + payload 加 content_fingerprint/original_url 可选字段）→ 状态机扩展（三个 _execute_* 方法；AUTOMATED 模式 source 必须 confirmed=True 区别于 MANUAL 归因新建待确认，保护已登记信源边界）→ 工具层（fetcher httpx + html_normalize BS4+SHA-256）→ Director（扫激活 IR × 已确认互联网途径笛卡尔积，产出内存 CollectionTask，不落账——decision-08）→ Collector.collect_outlet（前置指纹去重 → 命中追加转引链节点不调 LLM / 未命中调 LLM 抽取陈述，空陈述返回 None 但计量已发生）→ CLI（ir-create/ir-activate/collect 三子命令，每条 fetch+collect+execute 独立事务）。AC#1/AC#2 均以端到端等价路径（mock fetcher + fake LLM）走查 + 自动化测试双向验证，71 tests 全绿、覆盖率 95%；本地 docker compose 重建迁移自动跑、应用启动正常。AC↔测试映射：AC#1↔test_cli::test_ir_create_then_activate_then_collect_produces_lead（对应）+test_collector::test_collect_outlet_dedup_miss_calls_llm_and_returns_new_proposal、test_state_machine::test_automated_item_new_lands_lead_with_fingerprint_and_initial_node（支撑）；AC#2↔test_cli::test_collect_with_duplicate_content_appends_provenance_node（对应）+test_collector::test_collect_outlet_dedup_hit_returns_append_proposal_without_llm、test_state_machine::test_item_provenance_append_lands_node（支撑）。真实 LLM 走查需 LLM_API_KEY 且非阻塞——mock 测试已覆盖 AC 验证，按 doc-08 豁免规则留痕。decision-08「采集任务不落账（暂）」落档；情报需求模型豁免「提出方/生效窗口」在 comment 留痕（单消费方前提 + 调度节奏属后续范围）。
<!-- SECTION:FINAL_SUMMARY:END -->
