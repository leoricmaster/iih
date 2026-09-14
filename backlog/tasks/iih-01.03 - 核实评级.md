---
id: IIH-01.03
title: 核实评级
status: Done
assignee: []
created_date: '2026-09-10 12:50'
updated_date: '2026-09-14 09:27'
labels:
  - product
  - pipeline
milestone: m-0
dependencies:
  - IIH-01.02
references:
  - doc-04 §2.1
  - doc-02 §5
  - doc-06 §5
parent_task_id: IIH-01
priority: medium
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要已核实条目带二维评级，以便一眼判断情报可信度。

核实智能体最简版（doc-06 §5）：读候选、统计独立信源（穿透转引链，本里程碑单信源可简化）、按公式评内容可信度 1–6（数据设计 §2.1）、取信源画像可靠度 A–F 组装二维评级，落「已核实」。变量与结论分离：智能体测变量、公式出结论、公式版本记推理记录。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 一条「候选」态条目 When 核实智能体测得独立信源 N=1、出处信源可靠度 R=B Then 公式出内容可信度 2，组装评级 B2，状态迁移为「已核实」，公式版本记入推理记录
- [x] #2 Given 一条「候选」态条目 When 核实无法完成 Then 状态迁移为「存疑」挂起（可设复核期）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
# IIH-01.03 核实评级 — 实现计划

## Context

IIH-01.03 是单信源监控闭环的第三个故事：核实智能体最简版。前置 IIH-01.02 已落账 Candidate 态条目（审查通过），目前无核实入口。本任务实现 doc-06 §5 核实智能体最简版：读候选 → 穿透转引链统计独立信源 N → 取信源画像可靠度 R → 按公式（doc-04 §2.1）出内容可信度 1–6 → 组装二维评级（如 B2）→ 落「已核实」。变量与结论分离（decision-01）：N、R 是事实查询，公式是确定性映射，公式版本记入推理记录。

完成后 Candidate → Verified / Candidate → Undetermined 的状态迁移通路打通，为 IIH-01.04 收件箱浏览铺路。

## 设计决策（已与用户对齐）

1. **信源初始信用档**：严格按 doc-02 §5「反馈驱动」语义——`source.credit=None` 时无法取 R，走「存疑」路径（AC#2）。生产端到端要等 IIH-01.06 信用更新实现后才能产出已核实条目；IIH-01.03 自身 AC 通过测试预置 ORM 设 `credit="B"` 验证（与既有测试模式一致）。
2. **核实智能体不调 LLM**：本里程碑最简版的 N、R 均为事实查询，公式为确定性映射，无 LLM 判断场景。符合 doc-06 §1「成本纪律」与「判断归智能体，记账归确定性系统」。后续加厚反证/外部佐证/合并印证时再引入 LLM。Verifier 类仍置于 `agents/`，保留智能体语义结构（无状态、输出提案）。
3. **推理记录独立表**：新建 `VerificationRecord` 表，镜像 `ReviewDecision` 模式，持久化 N/R/rating/formula_version/rationale，满足 doc-08 #8「无溯源不落账」与 doc-04 §1 推理记录字段定义。

## 实现步骤

### A. 数据模型与迁移

**修改文件**：`src/iih/ledger/models.py`、`alembic/versions/<新>_verification_record.py`

新增枚举：
- `VerificationOutcome`: `VERIFIED` / `UNDETERMINED`

新增 `VerificationRecord` 模型：
- `id` PK
- `item_id` FK → intelligence_item.id, index
- `outcome` Enum(VerificationOutcome)
- `independent_source_count`: int（N；穿透转引链后的独立信源数）
- `source_reliability`: str(1) | None（R；VERIFIED 时必填，UNDETERMINED 时为空）
- `content_credibility`: int | None（1–6；VERIFIED 时必填，UNDETERMINED 时为空）
- `rating`: str(2) | None（如 "B2"；VERIFIED 时必填，UNDETERMINED 时为空）
- `formula_version`: str（如 "content_credibility_v1"；UNDETERMINED 时可为空或记 "n/a"）
- `rationale`: Text
- `created_at` DateTime server_default now()
- relationship: `item` back_populates="verification_records"，IntelligenceItem 加 `verification_records` 反向关系

迁移：down_revision = `a1b2c3d4e5f6`，新建 verification_record 表。

### B. 公式实现

**新建文件**：`src/iih/ledger/formula.py`

- `CONTENT_CREDIBILITY_FORMULA_VERSION = "content_credibility_v1"`
- `compute_content_credibility(n: int, r: str) -> int`：按 doc-04 §2.1 自上而下首个命中：
  - `n >= 2` → 1
  - `n == 1 and r in {"A", "B"}` → 2
  - `n == 1 and r == "C"` → 3
  - `n == 1 and r in {"D", "E"}` → 4
  - `n == 1 and r == "F"` → 6
  - 反证场景（n == 0 或其他）→ 5（本里程碑暂缓，公式保留分支位但不触发）
- `assemble_rating(r: str, credibility: int) -> str`：返回 `f"{r}{credibility}"`（如 "B2"）

### C. 提案契约扩展

**修改文件**：`src/iih/ledger/proposal.py`

新增：
- `VerificationPayload`: `item_id: int` + `outcome: VerificationOutcome` + `independent_source_count: int` + `source_reliability: str | None` + `content_credibility: int | None` + `rating: str | None`
- `VerificationProposal(Proposal)`: `PROPOSAL_TYPE = "intelligence_item_verification"`，`payload: VerificationPayload`，无 provenance，`formula_version` 字段记入 Proposal 顶层（继承自基类）

### D. 状态机扩展

**修改文件**：`src/iih/ledger/state_machine.py`

`execute()` match 加 `VerificationProposal` 分支；新增 `_execute_verification`：
- 校验：item 存在 + 当前状态为 CANDIDATE（前置）+ 依据非空 + outcome 合法
  - VERIFIED：`independent_source_count ≥ 1` + `source_reliability` 非空且为 A-F + `content_credibility` ∈ {1..6} + `rating` 非空
  - UNDETERMINED：`source_reliability`/`content_credibility`/`rating` 均为空
- VERIFIED：迁移 Candidate → Verified + 设 `item.rating = payload.rating` + 落 VerificationRecord
- UNDETERMINED：迁移 Candidate → Undetermined + 落 VerificationRecord（评级字段为空）
- 任一校验失败 → ProposalRejectedError，状态不变

### E. 核实智能体 Verifier

**新建文件**：`src/iih/agents/verifier.py`

类结构（不调 LLM，但保留智能体形态）：
- `AGENT_NAME = "verifier"`
- `__init__(self, session: Session)`（无 llm、无 model）
- 方法 `verify(self, item: IntelligenceItem) -> VerificationProposal`：
  1. 查 `item.provenance_nodes` → 统计独立信源 N = `len({node.source_id for node in nodes})`
  2. 取 R = `item.source.credit`（出处信源信用档）
  3. 若 R is None → 产出 UNDETERMINED 提案（依据："信源画像未设信用档，无法评定内容可信度"；formula_version=None 或 "n/a"）
  4. 若 R 有值 → 调 `compute_content_credibility(N, R)` 算 credibility → 调 `assemble_rating(R, credibility)` → 产出 VERIFIED 提案（formula_version=`CONTENT_CREDIBILITY_FORMULA_VERSION`）
- 不调 LLM、不计量（无 `LlmCall` 写入）

### F. CLI verify 子命令

**新建文件**：`src/iih/cli/verify.py`、**修改**：`src/iih/cli/__init__.py`

`verify.run(args)`：
1. 取 settings + engine + session_factory（不需要 llm 客户端）
2. 独立会话扫所有 Candidate 态条目 id 列表
3. 逐条：独立会话 → `Verifier.verify(item)` → `StateMachineExecutor().execute(proposal)` → 日志输出
4. 单条失败不阻断其他
5. 汇总统计：核实 N 条，已核实 X，存疑 Y，失败 Z

`cli/__init__.py` 注册 `verify` 子命令。

### G. 测试（TDD）

**修改文件**：`tests/test_state_machine.py`、`tests/test_verifier.py`（新建）、`tests/test_formula.py`（新建）、`tests/test_cli.py`、`tests/test_schema.py`

- `test_schema.py` 加 VerificationRecord VERIFIED/UNDETERMINED 两条 roundtrip 用例
- `test_formula.py` 新建：参数化覆盖公式所有分支（N≥2→1、N=1 R∈{A,B}→2、N=1 R=C→3、N=1 R∈{D,E}→4、N=1 R=F→6）+ assemble_rating
- `test_state_machine.py` 加：
  - VERIFIED 落账 Verified + item.rating + VerificationRecord
  - UNDETERMINED 落账 Undetermined + VerificationRecord（评级字段为空）
  - 前置违反（非 CANDIDATE）驳回
  - 字段缺失（依据空、VERIFIED 时缺 rating/source_reliability/content_credibility）驳回
  - VERIFIED 时 rating 与 source_reliability/content_credibility 一致性校验（可选）
  - item 不存在驳回
- `test_verifier.py` 新建：
  - AC#1 等价：Candidate + credit="B" + 单节点转引链 → VERIFIED 提案 + N=1 + R="B" + credibility=2 + rating="B2"
  - 公式覆盖：N=1 R=A/C/D/E/F 各分支
  - N=2 场景：预置 2 节点转引链（不同 source_id）→ credibility=1
  - AC#2 等价：Candidate + credit=None → UNDETERMINED 提案
  - 不调 LLM、不计量（无 LlmCall 写入）
- `test_cli.py` 加 verify 端到端：
  - VERIFIED 路径：Candidate + credit="B" → verify → Verified + rating="B2"
  - UNDETERMINED 路径：Candidate + credit=None → verify → Undetermined
  - 无 Candidate 优雅退出

### H. 本地门禁全绿 + 端到端走查

- `ruff check src tests` / `ruff format --check src tests` / `mypy src` / `pytest --cov`（≥80%）
- 干净环境 `docker compose down -v && up --build` → 迁移自动跑
- AC#1 端到端等价路径走查：Candidate + credit="B" + 单节点转引链 → Verifier.verify → VERIFIED + rating="B2" + VerificationRecord(formula_version="content_credibility_v1")
- AC#2 端到端等价路径走查：Candidate + credit=None → Verifier.verify → UNDETERMINED + VerificationRecord(rating=None)
- 真实环境端到端留豁免：生产链路需 IIH-01.06 设 credit 才能产出已核实条目，本里程碑 mock 测试已覆盖 AC 验证，按 doc-08 豁免规则留痕。

### I. 收尾

- `backlog task edit IIH-01.03 --plan <本计划>` 写入任务 plan
- `backlog task edit IIH-01.03 --status "In Progress"` 状态推进
- 实现完成后 `--check-ac 1 --check-ac 2 --check-dod 1`
- `--append-notes` 写阶段进展
- `--final-summary` 写完成总结
- commit 推送 main

## 关键文件路径

- 数据模型：`src/iih/ledger/models.py:244-267`（ReviewDecision 邻位新增 VerificationRecord + VerificationOutcome 枚举）
- 提案契约：`src/iih/ledger/proposal.py:134-159`（IIH-01.02 段末尾追加 VerificationProposal）
- 公式实现：`src/iih/ledger/formula.py`（新建）
- 状态机：`src/iih/ledger/state_machine.py:55-73`（execute match 分支）+ 末尾追加 `_execute_verification`
- 核实智能体：`src/iih/agents/verifier.py`（新建，参考 `src/iih/agents/reviewer.py:57-128` 结构）
- CLI：`src/iih/cli/verify.py`（新建，参考 `src/iih/cli/review.py:1-83`）+ `src/iih/cli/__init__.py:36-40` 注册子命令
- 迁移参考：`alembic/versions/a1b2c3d4e5f6_review_decision.py`（镜像模式）
- 状态机测试参考：`tests/test_state_machine.py:505-756`（IIH-01.02 段）
- 智能体测试参考：`tests/test_reviewer.py:1-181`

## 复用既有组件

- `StateMachineExecutor` / `ProposalRejectedError`（`src/iih/ledger/state_machine.py`）
- `make_engine` / `make_session_factory`（`src/iih/db.py`）
- `get_settings`（`src/iih/config.py`）
- 测试基建：`db_session` fixture（`tests/conftest.py:154-165`）、`_seed_lead_with_active_ir` 模式（`tests/test_state_machine.py:508-532`）改为 `_seed_candidate_with_credit`
- 公式版本号约定参考 doc-05 §5 提案契约 `formula_version` 字段

## 验证

1. **单元测试**：`pytest tests/test_formula.py tests/test_state_machine.py tests/test_verifier.py tests/test_cli.py tests/test_schema.py -v`
2. **覆盖率**：`pytest --cov --cov-report=term-missing`，确认新增代码覆盖率 ≥80%
3. **门禁**：`ruff check src tests && ruff format --check src tests && mypy src`
4. **端到端**（CLI 等价路径，需先有 Candidate 态条目）：
   ```bash
   python -m iih.cli ir-create --name "跟踪 W 公司" --spec "主题：矿卡"
   python -m iih.cli ir-activate 1
   python -m iih.cli collect     # 产出 Lead
   python -m iih.cli review      # Lead → Candidate
   python -m iih.cli verify      # Candidate → Verified 或 Undetermined
   ```
5. **干净环境**：`docker compose down -v && docker compose up --build` → 服务可用 + 迁移自动跑（head=<新 migration id>）

## 范围外（后续里程碑加厚）

- 反证判定（doc-04 §2.1 公式第 1 条「有反证但未证伪 → 5」）
- 外部信源检索佐证（doc-06 §5 工具栏）
- 合并印证（事件同一性命中并入既有条目，decision-02）
- 评级重评触发器（信源信用分档迁移 / 评级异议 / 人工触发，doc-02 §5.1）
- 转引链穿透至一次信源（本里程碑简化为 distinct source_id 计数）
- 存疑条目复核期设置（doc-06 §5「可设复核期」）
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
阶段 A 完成：models.py 加 VerificationOutcome 枚举（verified/undetermined）+ VerificationRecord 模型（item_id FK 索引 + outcome + independent_source_count + source_reliability String(1) + content_credibility int + rating String(2) + formula_version String(50) + rationale Text + created_at）。IntelligenceItem 加 verification_records 反向关系。迁移 b2c3d4e5f6a7_verification_record.py（down_revision=a1b2c3d4e5f6）。test_schema 加 VERIFIED/UNDETERMINED 两条 roundtrip 用例。

阶段 B 完成：新建 ledger/formula.py——CONTENT_CREDIBILITY_FORMULA_VERSION="content_credibility_v1" + compute_content_credibility(n, r, has_unrefuted_contradiction=False) 按公式表自上而下首个命中（反证→5、N≥2→1、N=1 R∈{A,B}→2、N=1 R=C→3、N=1 R∈{D,E}→4、完成评估但证据不足含 R=F→6）+ assemble_rating(r, credibility) 组装二维评级如 "B2"。test_formula 参数化覆盖全分支 + 边界值校验。

阶段 C 完成：proposal.py 加 VerificationPayload（item_id + outcome + independent_source_count + source_reliability optional + content_credibility optional + rating optional）+ VerificationProposal（PROPOSAL_TYPE=intelligence_item_verification，formula_version 继承自 Proposal 顶层）。无 provenance 字段（核实非采集动作，溯源五要素已在条目新建时落账）。

阶段 D 完成（TDD）：state_machine.py execute match 加 VerificationProposal 分支；新增 _execute_verification 方法内联校验——item 存在 + 状态为 CANDIDATE（前置）+ 依据非空 + VERIFIED 时 N≥1 + R∈{A-F} + credibility∈{1..6} + rating 非空，UNDETERMINED 时 R/credibility/rating 均空；VERIFIED 迁移 Candidate→Verified 并设 item.rating，UNDETERMINED 迁移 Candidate→Undetermined，落 VerificationRecord 记录（含 formula_version）。test_state_machine 加 12 用例（VERIFIED/UNDETERMINED 落账 + 前置违反/依据空/VERIFIED 缺 N/R/credibility/rating/非法 R/非法 credibility + UNDETERMINED 含评级字段驳回 + item 不存在）。

阶段 E 完成（TDD）：新建 agents/verifier.py——AGENT_NAME=verifier，构造仅 session（无 llm、无 model，本里程碑纯确定性）；verify(item) 方法：统计 provenance_nodes distinct source_id 得 N，取 item.source.credit 得 R，R=None 直接产出 UNDETERMINED 提案不调 LLM 不计量，R 有值调 compute_content_credibility+assemble_rating 产出 VERIFIED 提案，formula_version 记入提案顶层。test_verifier 7 用例（AC#1 N=1 R=B→B2、公式覆盖 R=A/B/C/D/E/F、N=2→B1、AC#2 credit=None→UNDETERMINED、不调 LLM 不计量、端到端 VERIFIED→Verified+Record、端到端 UNDETERMINED→Undetermined+Record）。

阶段 F 完成：新建 cli/verify.py——run(args) 扫 Candidate 态条目 id 列表，逐条独立会话 Verifier.verify → StateMachineExecutor.execute，单条失败不阻断，汇总已核实/存疑/失败统计；cli/__init__.py 注册 verify 子命令。test_cli 加 3 用例（VERIFIED 端到端→Verified+rating=B2、UNDETERMINED 端到端→Undetermined+rating=None、无 Candidate 优雅退出）。

阶段 G 完成：本地门禁全绿（ruff check All checks passed、ruff format --check 41 files formatted、mypy 27 files no issues、pytest 135 passed coverage 94%）。干净环境 docker compose down -v → up --build → 迁移自动跑 → Uvicorn running on http://0.0.0.0:8000；容器内验证 verification_record 表存在、字段齐备（outcome/independent_source_count/source_reliability/content_credibility/rating/formula_version/rationale/created_at）、迁移 head=b2c3d4e5f6a7。AC#1 端到端等价路径走查（test_verify_with_credit_b_produces_verified_b2 + test_verify_pass_then_execute_lands_verified_and_record + test_cli_verify_e2e_verified_transitions_to_verified）通过：Candidate + credit=B + 单节点转引链 → Verifier.verify → VERIFIED + rating=B2 + VerificationRecord(formula_version=content_credibility_v1, N=1, R=B, credibility=2)。AC#2 端到端等价路径走查（test_verify_no_credit_produces_undetermined + test_verify_no_credit_then_execute_lands_undetermined + test_cli_verify_e2e_undetermined_transitions_to_undetermined）通过：Candidate + credit=None → Verifier.verify → UNDETERMINED + VerificationRecord(rating=None, formula_version=None)。真实环境端到端需 IIH-01.06 设 credit 才能产出已核实条目——mock 测试已覆盖 AC 验证，按 doc-08 豁免规则留痕。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
实现 doc-06 §5 核实智能体最简版：读候选 → 穿透转引链统计独立信源 N → 取信源画像可靠度 R → 按公式（doc-04 §2.1）出内容可信度 1–6 → 组装二维评级（如 B2）→ 落「已核实」。变量与结论分离（decision-01）：N、R 是事实查询，公式是确定性映射，公式版本记入推理记录。本里程碑纯确定性，不调 LLM、不计量；credit=None → 存疑路径（AC#2）。

交付物：
- 数据模型：VerificationRecord 表（item_id + outcome + independent_source_count + source_reliability + content_credibility + rating + formula_version + rationale + created_at）+ 迁移 b2c3d4e5f6a7；IntelligenceItem 加 verification_records 反向关系
- 公式：ledger/formula.py（CONTENT_CREDIBILITY_FORMULA_VERSION=content_credibility_v1 + compute_content_credibility 按公式表自上而下首个命中 + assemble_rating 组装二维评级）
- 提案契约：VerificationPayload + VerificationProposal（formula_version 记入提案顶层，无 provenance）
- 状态机：_execute_verification 内联校验（状态前置 CANDIDATE + 依据非空 + VERIFIED 时 N≥1 + R∈{A-F} + credibility∈{1..6} + rating 非空，UNDETERMINED 时评级字段均空），VERIFIED→Verified+设 item.rating，UNDETERMINED→Undetermined，落 VerificationRecord
- 核实智能体 Verifier：无 LLM 纯确定性；verify(item) 统计 provenance_nodes distinct source_id 得 N，取 item.source.credit 得 R，R=None → UNDETERMINED 提案不调 LLM 不计量，R 有值 → VERIFIED 提案含公式版本
- CLI verify 子命令：批量扫 Candidate 全核实，单条失败不阻断
- 测试：135 passed coverage 94%；test_formula 参数化覆盖全分支，test_schema +2 用例，test_state_machine +12 用例，test_verifier 7 用例，test_cli +3 用例

门禁：ruff check / ruff format --check / mypy / pytest --cov 全绿。干净环境 docker compose 重建通过，迁移自动跑（head=b2c3d4e5f6a7），verification_record 表字段齐备。

范围外（后续里程碑加厚）：反证判定（公式第 1 条「有反证但未证伪 → 5」）、外部信源检索佐证、合并印证（事件同一性命中并入既有条目 decision-02）、评级重评触发器（信源信用分档迁移 / 评级异议 / 人工触发 doc-02 §5.1）、转引链穿透至一次信源、存疑条目复核期设置。
<!-- SECTION:FINAL_SUMMARY:END -->
