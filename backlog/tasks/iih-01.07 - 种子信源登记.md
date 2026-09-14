---
id: IIH-01.07
title: 种子信源登记
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-11 03:09'
updated_date: '2026-09-14 07:01'
labels:
  - product
  - ui
milestone: m-0
dependencies:
  - IIH-01.01
references:
  - doc-04
  - doc-07 §2.1/§3
  - prototype/index.html
parent_task_id: IIH-01
priority: high
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要在信源库登记种子信源及其首条互联网途径，以便闭环生产有源头可挂、信源信用有主体可记。

冷启动（doc-07 §2.1、原型「信源库」页）：登记表单按信源两分（见术语表 §六）拆主体字段与首条途径（如 W 公司 · 公司主体，官网 · 互联网途径），登记的互联网途径供自动拉取消费（IIH-01.08）。本里程碑只做登记与信源库列表浏览（主体/途径两栏）；画像与信用档展示随反馈驱动信用更新到场。范围外：实体挂接（实体归一后续）、待确认信源流（decision-05，属采集链）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 信源库为空 When 运维方登记主体「W 公司」（类型公司）及首条途径（官网 · 互联网）Then 信源库列表（主体/途径两栏）可见该信源（对照原型信源库页走查）
- [ ] #2 Given 登记表单必填字段缺失（主体名称/类型或途径媒介）When 提交 Then 校验拦截，不落账
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## 实现计划

### 设计抉择（已对齐）
1. 登记路径：扩展状态机执行器，新增 SourceRegisterProposal 提案类型（与 IIH-01.01 架构一致，记账层入口统一）。
2. 首条互联网途径必填：与原型 srcRegister() 对齐；种子信源无途径在 IIH-01.08 无消费价值。
3. Source.credit 初始 None：画像与信用档展示随 IIH-01.06 到场。
4. 导航最小化：仅信源库页加返回录入素材链接。

### 阶段 1 · 提案契约扩展（ledger/proposal.py）
- 新增 SourceRegisterPayload：source_name / source_type / outlet_name / outlet_entry
- 新增 SourceRegisterProposal：PROPOSAL_TYPE="source_register"；无 provenance（信源登记非情报产出）；无 formula_version

### 阶段 2 · 状态机执行器扩展（ledger/state_machine.py）
- execute() match 新增 SourceRegisterProposal 分支 → _execute_source_register
- 校验：4 字段非空白 + medium=internet 解析 + 信源名唯一 + 同主体途径名唯一
- 落账：Source(confirmed=True, credit=None) + Outlet(medium=internet, entry=...)
- 提案即事务单元，失败状态不变；ExecutionResult 扩展 source_id 字段

### 阶段 3 · 信源库 Web 页
- web/sources.py 新建：GET /sources 列表+表单、POST /sources 校验→提案→落账
- web/templates/sources.html 新建：列表（主体/途径两栏）+ 登记表单 + errors 回显
- web/app.py 注册 sources_router

### 阶段 4 · 测试（TDD）
- test_state_machine 新增 4 用例：落账 / 字段缺失驳回 / 信源名重复驳回 / 同主体途径名重复驳回
- test_web 新增 4 用例：列表渲染 / AC#1 端到端落账 / AC#2 表单拦截 / 驳回原因回显
- docstring 标 AC 引用，分「对应/支撑」两档

### 阶段 5 · 端到端验收
- AC#1 走查：登记主体「W 公司」+ 类型 company + 途径「官网」+ entry → 列表两栏可见
- AC#2 走查：必填缺失 → 表单拦截、不落账
- 干净环境 docker compose 重建可用（doc-08 #4）
- CI 全量绿（ruff/format/mypy/pytest-cov≥80，doc-08 #2/#3）

### 阶段 6 · 任务收尾
- 实现笔记按阶段落 Implementation Notes
- AC/DoD 勾选 + Final Summary
- 无 schema 变更 → 无 doc-04 更新；术语沿用 doc-03 §六无变更
<!-- SECTION:PLAN:END -->
