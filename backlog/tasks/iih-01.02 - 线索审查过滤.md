---
id: IIH-01.02
title: 线索审查过滤
status: Done
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-14 08:45'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-01.08
references:
  - doc-02 §4.3
  - doc-06 §4
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要审查智能体过滤线索，以便只有相关且有效的线索进入核实。

审查智能体最简版（doc-06 §4）：读线索、判相关性（对激活情报需求，本里程碑硬关联或简化匹配）与有效性初筛，产出审查提案——通过为候选、否决为噪音附理由。事件同一性/实体归一本里程碑最简或暂缓（单信源少冲突），后续加厚。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 一条「线索」态条目且与激活情报需求相关 When 审查智能体判定通过 Then 状态迁移为「候选」，提案落账
- [x] #2 Given 一条「线索」态条目且判定不相关 When 审查智能体否决 Then 状态迁移为「噪音」并附理由，提案落账
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
# IIH-01.02 线索审查过滤 — 实现计划

## Context

IIH-01.02 是单信源监控闭环的第二个故事：审查智能体最简版。前置任务 IIH-01.01/01.07/01.08 已建立素材录入、信源登记、互联网自动拉取链路，产出的 Lead 态条目目前无审查入口。本任务实现 doc-06 §4 审查智能体的最简版：读 Lead → 判相关性（对激活情报需求，LLM 判断）+ 有效性初筛 → 产出审查提案（通过为候选 / 否决为噪音附理由）。事件同一性、实体归一本里程碑暂缓（单信源少冲突）。

实现遵循既有架构原则：判断归智能体（LLM 判断相关性）、记账归确定性系统（状态机校验 + 落账）、无溯源不落账（审查依据持久化到 ReviewDecision 表）、智能体产出提案不直接写账。

完成后 Lead → Candidate / Lead → Noise 的状态迁移通路打通，为 IIH-01.03 核实评级铺路。

## 设计决策（已与用户对齐）

1. **审查依据落账**：新增 `ReviewDecision` 表（item_id + decision + reason_type + matched_requirement_id + rationale + created_at），每次审查落一条，与 ProvenanceChainNode 同风格事件性记账，满足 doc-08 #8。
2. **相关性算法**：LLM 判断（陈述 + 激活情报需求 content_spec → decision + matched_requirement_id + rationale），与 Collector 归因/抽取同构。
3. **CLI 范围**：批量扫 Lead 全审查，与 collect 链路对称。

## 实现步骤

### A. 数据模型与迁移

**修改文件**：`src/iih/ledger/models.py`、`alembic/versions/<新>_review_decision.py`

新增枚举：
- `ReviewDecisionEnum`: `PASS` / `REJECT`
- `RejectionReasonEnum`: `IRRELEVANT` / `DUPLICATE` / `INVALID`（本里程碑只用 IRRELEVANT + INVALID，DUPLICATE 留枚举位以备事件同一性加厚）

新增 `ReviewDecision` 模型：
- `id` PK
- `item_id` FK → intelligence_item.id, index
- `decision` Enum(ReviewDecisionEnum)
- `reason_type` Enum(RejectionReasonEnum) | None（PASS 时为空）
- `matched_requirement_id` FK → intelligence_requirement.id | None（REJECT 时为空）
- `rationale` Text
- `created_at` DateTime server_default now()
- relationship: `item` back_populates="review_decisions"，IntelligenceItem 加 `review_decisions` 反向关系

迁移：down_revision = `f7a2c91b3e4d`，新建 review_decision 表。

### B. 提案契约扩展

**修改文件**：`src/iih/ledger/proposal.py`

新增：
- `ReviewPayload`: `item_id: int` + `decision: ReviewDecisionEnum` + `reason_type: RejectionReasonEnum | None` + `matched_requirement_id: int | None`
- `ReviewProposal(Proposal)`: `PROPOSAL_TYPE = "intelligence_item_review"`，`payload: ReviewPayload`，无 provenance、无 formula_version（审查非情报产出）

### C. 状态机扩展

**修改文件**：`src/iih/ledger/state_machine.py`

`execute()` match 加 `ReviewProposal` 分支；新增 `_execute_review`：
- 校验：item 存在 + 当前状态为 LEAD（前置）+ rationale 非空 + decision 合法
  - PASS 时：matched_requirement_id 必填 + 需求存在 + 状态为 ACTIVE
  - REJECT 时：reason_type 必填
- PASS：迁移 Lead → Candidate + 落 ReviewDecision(decision=PASS, matched_requirement_id, rationale)
- REJECT：迁移 Lead → Noise + 落 ReviewDecision(decision=REJECT, reason_type, rationale)
- 任一校验失败 → ProposalRejectedError，状态不变

### D. 审查智能体 Reviewer

**新建文件**：`src/iih/agents/reviewer.py`

类结构镜像 Collector：
- `AGENT_NAME = "reviewer"`
- `__init__(self, llm: Instructor, session: Session, model: str)`
- LLM schema `ReviewJudgmentResult`: `decision: ReviewDecisionEnum` + `reason_type: RejectionReasonEnum | None` + `matched_requirement_id: int | None` + `rationale: str`
- 系统提示词：判断陈述是否与任一激活情报需求相关 + 陈述是否有效（客观、非空、非纯评价）；通过须填 matched_requirement_id；否决须填 reason_type（IRRELEVANT 或 INVALID）
- 方法 `review(self, item: IntelligenceItem) -> ReviewProposal`：
  1. 查激活情报需求列表（status=ACTIVE）
  2. 无激活需求 → 直接产出 REJECT/IRRELEVANT 提案（不调 LLM、不计量；依据为"无激活情报需求"）
  3. 有激活需求 → 调 LLM 判断 → 产出 ReviewProposal（含 matched_requirement_id 或 reason_type）
  4. LLM 调用计量入账（`_meter(target="item_review", ...)`）
- 工具：线索与既有条目读取、需求读取（doc-06 §4）

### E. CLI review 子命令

**修改文件**：`src/iih/cli/review.py`（新建）、`src/iih/cli/__init__.py`

`review.run(args)`：
1. 取 settings + engine + session_factory + llm 客户端
2. 独立会话扫所有 Lead 态条目
3. 逐条：独立会话 → `Reviewer.review(item)` → `StateMachineExecutor().execute(proposal)` → 日志输出
4. 单条失败（LLM 异常 / 提案驳回）不阻断其他
5. 汇总统计：审查 N 条，通过 X，否决 Y，失败 Z

`cli/__init__.py` 注册 `review` 子命令。

### F. 测试（TDD）

**修改文件**：`tests/conftest.py`、`tests/test_state_machine.py`、`tests/test_reviewer.py`（新建）、`tests/test_cli.py`、`tests/test_schema.py`

- `conftest.py` 加 `make_fake_llm_review(judgment)` 替身工厂 + `w_review_pass` / `w_review_reject` fixture
- `test_schema.py` 加 ReviewDecision roundtrip 用例
- `test_state_machine.py` 加：
  - PASS 落账 Candidate + ReviewDecision
  - REJECT 落账 Noise + ReviewDecision
  - 前置违反（非 LEAD）驳回
  - 字段缺失（rationale 空、PASS 时 matched_requirement_id 缺、REJECT 时 reason_type 缺）驳回
  - matched_requirement 不存在 / 非 ACTIVE 驳回
- `test_reviewer.py` 新建：
  - LLM 通过路径产出 PASS 提案 + matched_requirement_id
  - LLM 否决路径产出 REJECT 提案 + reason_type
  - 无激活情报需求时直接 REJECT（不调 LLM、不计量）
  - LLM 计量入账
- `test_cli.py` 加 review 端到端：落账 Lead → 跑 review 子命令 → 状态迁移为 Candidate/Noise

### G. 本地门禁全绿 + 端到端走查

- `ruff check` / `ruff format --check` / `mypy` / `pytest --cov`（≥80%）
- 干净环境 `docker compose down -v && up --build` → 迁移自动跑
- AC#1 端到端等价路径：Lead + 激活 IR → Reviewer.review → PASS → Candidate + ReviewDecision(matched_requirement_id, rationale)
- AC#2 端到端等价路径：Lead + 激活 IR 但陈述不相关 → Reviewer.review → REJECT/IRRELEVANT → Noise + ReviewDecision(reason_type, rationale)
- 真实 LLM 走查留豁免（非阻塞，mock 测试已覆盖 AC）

### H. 收尾

- `backlog task edit IIH-01.02 --plan <本计划>` 写入任务 plan
- `backlog task edit IIH-01.02 --status "In Progress"` 状态推进
- 实现完成后 `--check-ac 1 --check-ac 2 --check-dod 1`
- `--append-notes` 写阶段进展
- `--final-summary` 写完成总结
- commit 推送 main

## 关键文件路径

- 数据模型：`src/iih/ledger/models.py:111-221`（IntelligenceItem / ProvenanceChainNode 邻位新增 ReviewDecision）
- 提案契约：`src/iih/ledger/proposal.py:1-132`（末尾追加 ReviewProposal）
- 状态机：`src/iih/ledger/state_machine.py:55-68`（execute match 分支）+ 末尾追加 `_execute_review`
- 采集智能体参考：`src/iih/agents/collector.py:67-192`（Reviewer 镜像此结构）
- 采集 CLI 参考：`src/iih/cli/collect.py:1-82`（review 链路镜像）
- 迁移参考：`alembic/versions/f7a2c91b3e4d_ir_provenance_chain.py`
- 测试基建：`tests/conftest.py:18-49`（fake_llm 工厂模式）
- 状态机测试：`tests/test_state_machine.py:228-498`（IIH-01.08 段参考）

## 复用既有组件

- `StateMachineExecutor` / `ProposalRejectedError`（`src/iih/ledger/state_machine.py`）
- `make_llm_client` / `Instructor` 结构化输出（`src/iih/agents/llm.py`）
- `make_engine` / `make_session_factory`（`src/iih/db.py`）
- `get_settings`（`src/iih/config.py`）
- `LlmCall` 计量模型（`src/iih/ledger/models.py:111-122`）
- 测试基建：`db_session` fixture、`make_fake_llm_*` 工厂模式（`tests/conftest.py`）

## 验证

1. **单元测试**：`pytest tests/test_state_machine.py tests/test_reviewer.py tests/test_cli.py tests/test_schema.py -v`
2. **覆盖率**：`pytest --cov --cov-report=term-missing`，确认新增代码覆盖率 ≥80%
3. **门禁**：`ruff check src tests && ruff format --check src tests && mypy src`
4. **端到端**（CLI 等价路径）：
   ```bash
   python -m iih.cli ir-create --name "跟踪 W 公司" --spec "主题：矿卡、订单、战略"
   python -m iih.cli ir-activate 1
   python -m iih.cli collect  # 产出 Lead
   python -m iih.cli review   # Lead → Candidate 或 Noise
   ```
5. **干净环境**：`docker compose down -v && docker compose up --build` → 服务可用 + 迁移自动跑

## 范围外（后续里程碑加厚）

- 事件同一性判定（doc-06 §4，DUPLICATE 否决路径）
- 实体归一（doc-06 §4，实体同一性判定）
- 图连通度参考变量、断连孤岛新话题提示
- 调度自动触发审查（本里程碑 CLI 手动触发）
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
阶段 A 完成：models.py 加 ReviewDecisionEnum（pass/reject）+ RejectionReasonEnum（irrelevant/duplicate/invalid，本里程碑只用前两个，duplicate 留枚举位以备事件同一性加厚）+ ReviewDecision 模型（item_id FK 索引 + decision + reason_type + matched_requirement_id FK + rationale Text + created_at）。IntelligenceItem 加 review_decisions 反向关系。迁移 a1b2c3d4e5f6_review_decision.py（down_revision=f7a2c91b3e4d）。test_schema 加 ReviewDecision PASS/REJECT 两条 roundtrip 用例。

阶段 B 完成：proposal.py 加 ReviewPayload（item_id + decision + reason_type optional + matched_requirement_id optional）+ ReviewProposal（PROPOSAL_TYPE=intelligence_item_review，无 provenance、无 formula_version）。依据记入 rationale，落账时持久化到 ReviewDecision 表以满足 doc-08 #8。

阶段 C 完成（TDD）：state_machine.py execute match 加 ReviewProposal 分支；新增 _execute_review 方法内联校验——item 存在 + 状态为 LEAD（前置）+ 依据非空 + PASS 时 matched_requirement_id 必填且需求存在且 ACTIVE + REJECT 时 reason_type 必填；PASS 迁移 Lead→Candidate，REJECT 迁移 Lead→Noise，落 ReviewDecision 记录。test_state_machine 加 9 用例（PASS/REJECT 落账 + 前置违反/字段缺失/PASS 缺 matched/REJECT 缺 reason_type/matched 不存在/matched 非 ACTIVE 驳回）。

阶段 D 完成（TDD）：新建 agents/reviewer.py——AGENT_NAME=reviewer，构造同 Collector；ReviewJudgmentResult instructor schema（decision + reason_type + matched_requirement_id + rationale）；REVIEW_SYSTEM_PROMPT 两维度判断（相关性 + 有效性）；review(item) 方法：无激活 IR 直接 REJECT/IRRELEVANT 不调 LLM 不计量，有激活 IR 调 LLM 判断产出 ReviewProposal，_meter(target=item_review) 即时计量。test_reviewer 5 用例（PASS/REJECT irrelevant/REJECT invalid/无 IR 短路/端到端 PASS→Candidate+ReviewDecision）。

阶段 E 完成：新建 cli/review.py——run(args) 扫 Lead 态条目 id 列表，逐条独立会话 Reviewer.review → StateMachineExecutor.execute，单条失败不阻断，汇总通过/否决/失败统计；cli/__init__.py 注册 review 子命令。test_cli 加 3 用例（PASS 端到端→Candidate、REJECT 端到端→Noise、无 Lead 优雅退出）。

阶段 F 完成：conftest.py 加 make_fake_llm_review 替身工厂 + w_review_pass_factory（动态传 IR id）+ w_review_reject_irrelevant/invalid fixture。

阶段 G 完成：本地门禁全绿（ruff check All checks passed、ruff format --check 干净、mypy 24 files no issues、pytest 90 passed coverage 95%）。干净环境 docker compose down -v → up --build → 迁移自动跑 → Uvicorn running on http://0.0.0.0:8000；容器内验证 review_decision 表存在、字段齐备、迁移 head=a1b2c3d4e5f6。AC#1 端到端等价路径走查（test_review_pass_then_execute_lands_candidate_and_decision + test_cli_review_e2e_pass_transitions_to_candidate）通过：Lead + 激活 IR → Reviewer.review → PASS → Candidate + ReviewDecision(matched_requirement_id, rationale)。AC#2 端到端等价路径走查（test_review_reject_irrelevant_produces_proposal_with_reason + test_cli_review_e2e_reject_transitions_to_noise）通过：Lead + 激活 IR 但陈述不相关 → Reviewer.review → REJECT/IRRELEVANT → Noise + ReviewDecision(reason_type, rationale)。真实 LLM 走查需 LLM_API_KEY 且非阻塞——mock 测试已覆盖 AC 验证，按 doc-08 豁免规则留痕。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
实现 doc-06 §4 审查智能体最简版：读 Lead → 判相关性（对激活情报需求，LLM 判断）+ 有效性初筛 → 产出审查提案（通过为候选 / 否决为噪音附理由）。事件同一性、实体归一本里程碑暂缓。

交付物：
- 数据模型：ReviewDecision 表（item_id + decision + reason_type + matched_requirement_id + rationale + created_at）+ 迁移 a1b2c3d4e5f6；IntelligenceItem 加 review_decisions 反向关系
- 提案契约：ReviewPayload + ReviewProposal（无 provenance，依据记入 rationale 持久化到 ReviewDecision 满足 doc-08 #8）
- 状态机：_execute_review 内联校验（状态前置 LEAD + 依据非空 + PASS 时 matched_requirement 必填且 ACTIVE + REJECT 时 reason_type 必填），PASS→Candidate、REJECT→Noise
- 审查智能体 Reviewer：无激活 IR 短路 REJECT/IRRELEVANT 不调 LLM；有激活 IR 调 LLM 判断相关性 + 有效性，产出 ReviewProposal，计量入账
- CLI review 子命令：批量扫 Lead 全审查，单条失败不阻断
- 测试：90 passed coverage 95%；test_state_machine +9 用例，test_reviewer 5 用例，test_cli +3 用例，test_schema +2 用例

门禁：ruff check / ruff format --check / mypy / pytest --cov 全绿。干净环境 docker compose 重建通过，迁移自动跑。

范围外（后续里程碑加厚）：事件同一性（DUPLICATE 否决路径）、实体归一、图连通度参考变量、调度自动触发审查。
<!-- SECTION:FINAL_SUMMARY:END -->
