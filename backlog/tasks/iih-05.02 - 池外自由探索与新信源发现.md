---
id: IIH-05.02
title: 池外自由探索与新信源发现
status: In Progress
assignee: []
created_date: '2026-09-15 12:31'
updated_date: '2026-09-16 13:51'
labels:
  - product
dependencies:
  - IIH-05.01
references:
  - decision-05
  - doc-06 §3
  - IIH-01.08
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 19002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要采集执行时按配置比例探索监控池外、上报发现的新信源，以便不主动搜索也能持续发现值得纳入的新信源，经我确认后扩大信源覆盖（decision-05 通道二）。

现状：采集智能体仅执行派单任务，无池外探索；新信源发现提案类型在 doc-06 §3 已设计、未实现；待确认队列与确认入口由待确认信源确认闭环单建立。

范围：采集智能体执行采集任务时按配置比例做池外自由探索；发现的新信源产出新信源发现提案（含发现来源与依据），进入待确认队列，经确认入口入池，与人工归因产生的待确认信源同通路。前置裁决：探索判断归采集智能体（doc-06 现状）或定向智能体加厚；探索比例的配置粒度（全局起步或需求级）。

范围外：探索方向的人工引导（研究课题联动）；新信源画像自动生成；信源库既有信源的相似去重提示。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given 池外探索开启（比例大于 0）When 采集智能体执行采集任务 Then 按配置比例执行池外探索，发现的新信源产出新信源发现提案进入待确认队列
- [x] #2 Given 新信源发现提案 When 消费方经确认入口确认 Then 该信源入信源库并可被情报需求绑定与调度派单
- [x] #3 Given 新信源发现提案未经确认 When 调度与记账运行 Then 该信源不入信源库、不建画像、不参与信用记账（decision-05）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [x] #2 探索比例默认值为 0，不影响既有采集行为；比例配置不经改代码可调
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## 实现计划（修订版 · 检索式池外探索）

### 前置裁决（已确认）
1. 探索判断归采集智能体（采纳 doc-06 §3 现状）
2. 探索比例配置粒度：需求级（IR.explore_ratio 字段，None=0）
3. 探索动作：**改为互联网检索式（Tavily Search API）**——初版「入口页外链衍生」对 JS 渲染站点失效，用户裁决改检索式
4. 新信源发现提案为独立类型 source_discovery
5. 检索工具：Tavily Search API（外购，不入 ADR，落 doc-05 §4 工具层）
6. 检索词：LLM 从 IR.content_spec 提取 2–4 关键词
7. 选链策略：LLM 从 top-5 选链（排除本途径域）

### 阶段 1 · 模型与迁移
- IntelligenceRequirement.explore_ratio: float | None（None=0；默认 None）+ alembic 迁移 n3o4p5q6r7s8
- IntelligenceRequirementRegisterPayload.explore_ratio: float | None = None
- CollectionTask 加 explore_ratio + content_spec 字段（Director 从 IR 注入）

### 阶段 2 · 提案契约
- SourceDiscoveryPayload{source_name, source_type} + SourceDiscoveryProposal（source_discovery）

### 阶段 3 · 状态机
- _execute_source_discovery：校验 + 落账 confirmed=False + 撞名驳回（含别名）

### 阶段 4 · 采集智能体（检索式探索）
- 新 prompts：EXPLORATION_KEYWORD / EXPLORATION_RESULT_SELECTION / EXPLORATION_ATTRIBUTION
- collect_outlet 末尾按 task.explore_ratio 概率调 _explore_outside_pool
- _explore_outside_pool：content_spec → LLM 提取关键词 → Tavily 检索 top-5 → LLM 选链（排除本途径域）→ fetch → 归一化 → LLM 归因 → 不在信源库产出 SourceDiscoveryProposal
- 沿用既有 _collect_outlet_main 两跳主任务，探索为副产品
- content_spec 空 / 检索失败 / 无外域候选 / 撞名 / 无主体 / 抓取或 LLM 失败一律静默跳过

### 阶段 R1 · Tavily 客户端
- src/iih/tools/search.py：Tavily search 客户端 + SearchError + SearchResult{url, title, content}
- Settings 加 tavily_api_key；.env.example + docker-compose 注入同步

### 阶段 R2 · 改造探索链路
- collector.py 改 _explore_outside_pool 为检索式（见阶段 4）
- Collector 内通过 search_module.search 访问便于测试 monkeypatch
- Web 试采集预览强制 explore_ratio=0 避免 Tavily 副作用

### 阶段 R3 · 测试
- conftest 加 make_fake_tavily 替身；ExplorationKeywordResult / ExplorationResultSelectionResult 替身
- test_collector 6 用例（explore_ratio=0 / =1 触发 / 撞已登记 / 无主体 / 检索失败不阻断 / content_spec 空）
- test_state_machine 与 test_web 不变（AC#2/#3 走状态机注入 + Web 表单）

### 阶段 R4 · 文档与收尾
- doc-05 §4 工具层补检索侧选型说明（Tavily 选型理由 + 降级语义）
- doc-06 §3 输出栏改写为「检索式池外探索实现」
- 本地门禁 + docker 重建浏览器走查 AC#1/#2/#3（含真实 Tavily 调用）
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
实现概要（修订版 · 检索式池外探索）：

【改造缘起】初版「入口页外链衍生」对 JS 渲染站点（三一集团 Nuxt.js 官网）失效，且闭环窄、与「池外」语义偏差；用户裁决改为互联网检索式，工具选型 Tavily Search API（不落 ADR，进设计文档）。

- 工具层（src/iih/tools/search.py）：Tavily 客户端 search(query, api_key, max_results=5) → list[SearchResult]{url, title, content}；失败抛 SearchError。Settings 加 tavily_api_key（.env 同步、compose 注入）。
- 提案契约：SourceDiscoveryPayload + SourceDiscoveryProposal（source_discovery）保持不变。
- 状态机：_execute_source_discovery 不变（落账 confirmed=False + 撞名驳回）。
- 采集智能体（agents/collector.py）：_explore_outside_pool 改为「IR.content_spec → LLM 提取 2–4 关键词 → Tavily 检索 top-5（排除本途径域）→ LLM 选链 → fetch → 归一化 → LLM 归因 → 信源名不在信源库（含别名）产出 SourceDiscoveryProposal 直接落账」；content_spec 空 / 检索失败 / 无外域候选 / 撞名 / 无主体 / 抓取或 LLM 失败一律静默跳过；计量 LlmCall(target=outlet_exploration) ×3（关键词+选链+归因）。
- CollectionTask 加 content_spec 字段；Director 从 IR.content_spec 注入；Web 试采集预览强制 explore_ratio=0 避免副作用。
- 测试：conftest 加 make_fake_tavily + ExplorationKeywordResult / ExplorationResultSelectionResult 替身；test_collector 6 用例（explore_ratio=0 不探索 / =1 触发新信源落账 / 撞已登记信源跳过 / 无主体跳过 / Tavily 检索失败不阻断主任务 / content_spec 空跳过）；test_state_machine 与 test_web 用例不变。
- 文档：doc-05 §4 工具层补检索侧选型说明；doc-06 §3 输出栏改写为「检索式池外探索实现」。
- 门禁：ruff check/format 绿；mypy src 42 文件无问题；pytest 371 passed 覆盖 89%。
- Docker 重建真实走查（Tavily 真实调用）：
  - AC#1：IR#1 explore_ratio=1 → POST /pipeline/run → 一轮触发 21 次 outlet_exploration LLM 调用 → 真实产出待确认信源「证券时报社」（id=28，confirmed=False，type=media）进队列；
  - AC#2：POST /sources/28/confirm（initial_credit=C）→ 入信源库 confirmed=True credit=C；POST /requirements 绑定 source 28 → 草稿 IR#7；POST /requirements/7/action（activate）→ 激活成功，派单资格生效；
  - AC#3：注入未确认信源 source 29 → POST /requirements 绑定 → Web 层校验拒绝「信源不可绑定：29」、IR 未落账；
  - 临时数据已清理，dev 库恢复 7 信源 + 1 IR 原状。

【验收补救 · 第 1 轮（2026-09-16，走查 4 项 UI/UX 发现并入本单）】
1. 收件箱拆分（doc-07 §2/§3 修订）：警报独立入导航置灰占位；收件箱删「警报」「待确认信源」区块，只留待反馈 + 存疑指引；待确认信源计数徽标挂信源库导航（context.sources_pending_count）。
2. 状态筛选去复合（doc-07 §2 修订）：删「已核实起」复合标签；状态行互斥单选六状态 + 全部，默认「已核实」（与收件箱待反馈同口径）。
3. 处置独立成维度（doc-02 §4/§6 对齐）：列表页加「处置」窄列（—/作废）与独立筛选（全部/未作废/已作废）；详情页状态与作废 pill 拆开、元数据加处置行；「作废」chip 移出状态行。
4. 后端状态门：FeedbackRouter FACTUAL_ERROR 仅对已核实条目开放（doc-02 §4「作废打在已核实条目上」），堵住「噪音+作废」异常数据来源；既有异常条目待用户裁决是否清理。
测试：test_web 更新（导航含警报、默认已核实、处置正交、信源库徽标、确认入口三处）+ test_feedback_router 加状态门用例；374 passed 覆盖 89.5%；ruff/mypy 绿；Docker 重建后逐页核对。

【验收补救 · 第 2 轮（2026-09-16，发现信源带途径 + 后台循环加固）】
- 根因：①发现来源 URL 只记在提案 rationale、落账即丢弃，确认入池也不建途径——发现信源与人工登记信源不同构（无采集入口，入池后仍不可被采集）；②后台采集循环的 asyncio task 无强引用被 GC 静默回收（循环停摆无报错），tick INFO 日志又被 uvicorn 默认配置吞掉、不可发现。
- 发现信源带途径：Source.discovered_entry 可空列（迁移 o4p5q6r7s8t9）；SourceDiscoveryPayload 加必填 outlet_entry（发现来源 URL 落账 discovered_entry，rationale 去重）；SourceConfirmPayload 加 outlet_name/outlet_entry——确认携带采集入口即建互联网途径（名默认「网站」可改；并入路径建到目标信源、同名跳过；留空不建，兼容人工归因的待确认信源）；待确认行内途径名/采集入口输入（预填发现 URL）；collector 传 target_url 入 payload。doc-04（实体属性表 + §2.3 确认措辞）、doc-06 §3 同步。
- 循环加固：loop task 挂 app.state.pipeline_loop_task 强引用（防 GC）；logging.basicConfig(INFO) 使 tick 日志可见（停摆可发现）。
- 遗留：旧代码发现的 9 行待确认信源 discovered_entry 为 NULL，确认时可手填采集入口（留空不建途径）。
- 验证：379 passed 覆盖 89.5%；ruff/mypy 绿；Docker 重建后核对（迁移生效、待确认行途径输入、tick 日志可见且循环存活）。
<!-- SECTION:FINAL_SUMMARY:END -->
