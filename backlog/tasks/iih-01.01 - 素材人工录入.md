---
id: IIH-01.01
title: 素材人工录入
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-10 12:50'
updated_date: '2026-09-11 11:34'
labels:
  - product
  - ui
milestone: m-0
dependencies: []
references:
  - doc-07 §2.3
  - doc-06 §3
  - doc-05 §4/§5/§8
  - prototype/index.html
  - doc-04 §1
  - doc-02 §4.3
  - doc-03 §三/§六
  - decision-05
parent_task_id: IIH-01
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要录入素材产出线索，以便把线下拿到的情报送进流水线。

录入素材页（doc-07 §2.3、原型「录入素材」页）：选媒介、填写陈述内容，提交生成线索提案，经状态机执行器落账为「线索」态，溯源五要素齐备。信源与途径不经登记、由采集智能体从陈述归因补记（接 LLM 最简归因：推断信源与途径；非互联网途径不经登记，doc-06 §3）；识别出未登记信源则经双通道确认制准入（decision-05）。

本故事范围（奠基裁夺）：仅文字载体录入；附件载体管线（录音 ASR / 图片 OCR / 文档解析）剥离至 IIH-01.09 / IIH-01.10 / IIH-01.11（非 MVP），实体提及抽取剥离至 IIH-01.12（非 MVP）。承载奠基工作包：提案契约与状态机执行器、工程骨架与 CI 基线（选型见技术架构 §1/§3、质量保障见 §8），实现计划于开发启动时编写。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方打开录入素材页 When 选媒介「会议讨论」、填写陈述「W 公司渠道大会：下一代电驱矿卡计划 2027Q2 量产」、提交 Then 生成线索提案，落账为「线索」态；信源（W 公司）与途径（渠道大会现场）由采集智能体归因补记（非互联网途径不经登记，doc-06 §3），溯源五要素齐备（载体+媒介+采集时间+原文快照+信源/途径归因）（对照原型录入素材页走查）
- [ ] #2 Given 运维方录入时必填字段缺失 When 提交 Then 表单校验拦截，不生成提案
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## 实现计划

### 阶段 0 · 工程骨架（doc-05 §3）
- pyproject.toml：fastapi / sqlalchemy / alembic / psycopg / jinja2 / openai + instructor（LLM 结构化输出）/ pytest / pytest-cov / ruff / mypy；ruff·mypy·pytest 配置就位
- docker-compose.yml：web-app 单体 + postgres + 文件存储卷；Dockerfile
- 配置层：DATABASE_URL、LLM_*（provider/model/base_url/api_key）走环境变量，不入库不入 git（doc-05 §7）
- FastAPI 入口 + 健康检查（连库探活）
- 分包基线（镜像 doc-05 §4 三层）：ledger/（状态机执行器、提案契约、溯源存储）、agents/（Collector）、tools/、web/（FastAPI + Jinja2）

### 阶段 1 · 最简 schema（doc-04 §1，English 命名见术语表 §三/§六）
- SQLAlchemy models：Medium、Modality、Source、Outlet、IntelligenceItem（status / rating / void_flag / provenance 五要素 / provenance_source / event_time / mode）
- Source 加待确认状态：归因产出的新信源记待确认、不入正式池不参与信用（decision-05），确认入信源库归 IIH-01.07
- EntityMention 表随 IIH-01.12，本任务不建
- Alembic 初始迁移建表

### 阶段 2 · CI 基线（doc-05 §8、doc-08）
- .github/workflows/ci.yml：push 到 main 触发，门禁 ruff check → ruff format --check → mypy → pytest --cov（--cov-fail-under=80，全仓口径）
- 本地 pytest 可跑、覆盖率报告生成

### 阶段 3 · 提案契约与状态机执行器（doc-05 §4/§5、doc-02 §4.3）
- 提案契约结构：类型 / 产出 / 依据 / 溯源 / 公式版本
- 状态机执行器：接收提案 → 校验（字段完整、状态前置、溯源必填）→ 迁移 → 写溯源存储；失败驳回、状态不变、事务原子；无溯源不落账由校验强制
- 第一个提案类型「情报条目新建」：迁移 [*] → Lead
- 单测：通过落账 / 溯源缺失驳回 / 前置违反驳回，进 CI 回归

### 阶段 4 · 采集智能体 Collector · 最简归因（doc-06 §3）
- Collector 执行器包（agents/）：人工提交路径不经定向任务化、直接产出线索提案
- LLM 最简归因：从陈述 + 媒介推断 Source（发布主体）+ Outlet（线下场景途径），组装溯源五要素；实体提及抽取剥离至 IIH-01.12
- LLM 集成：OpenAI 客户端 + instructor（Pydantic 结构化输出归因字段）；起步接 DeepSeek（OpenAI 兼容端点）；provider/model/base_url/api_key 走环境变量——切 provider 只改配置不动代码；SDK 直连、调用计量入 PG（最简计量表：智能体/对象/token/时间）
- 测试用 LLM mock

### 阶段 5 · 录入素材页（doc-07 §2.3、原型）
- FastAPI + Jinja2 服务端渲染：媒介下拉（封闭集合，互联网排除——互联网为自动拉取不走本页）、陈述文本框、提交
- 表单校验：必填缺失拦截、不生成提案（AC#2）
- 提交 → Collector → 线索提案 → 状态机执行器落账 Lead（AC#1 端到端）
- 近期人工提交列表（进度可见，对照原型）

### 阶段 6 · 端到端验收
- AC#1 走查（媒介「会议讨论」+ 陈述 → 落账 Lead、溯源五要素齐备）、AC#2 走查（必填缺失拦截）
- 干净环境一条命令重建（doc-08 #4）、CI 全量绿（doc-08 #2/#3）
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
阶段 0 完成：pyproject（uv 管理依赖+锁文件）、docker-compose（web-app+postgres+文件卷）、Dockerfile、配置层（DATABASE_URL/FILE_STORAGE_DIR/LLM_* 环境变量）、FastAPI 入口+/healthz 连库探活、三层分包基线（ledger/agents/tools/web）。pytest 1 passed、ruff/format/mypy 全绿、覆盖率 100%。

阶段 1 完成：ledger/models.py（Medium/Modality/Source 含待确认位/Outlet/IntelligenceItem：status·rating·retracted·mode·溯源五要素·provenance_source·event_time）；Alembic 初始迁移含媒介/载体 seed（术语表封闭集合，媒介用「内部会议」）；测试库独立（iih_test）+ 每测试事务回滚。发现：原型与 AC 写「会议讨论」，术语表为「内部会议」，已按术语表实现，待用户裁决 AC 措辞。

阶段 2 完成：.github/workflows/ci.yml，push main 触发，门禁 ruff check → ruff format --check → mypy → pytest --cov-fail-under=80（全仓口径），postgres service 容器供测试。CI 实际跑绿待首次 push 验证（阶段 6）。

阶段 3 完成（TDD）：ledger/proposal.py 提案契约（类型/产出/依据/溯源/公式版本，首个类型 intelligence_item_new）+ ledger/state_machine.py 状态机执行器（校验字段完整·状态前置·溯源必填 → 迁移 Lead → 落账；驳回状态不变、提案即事务单元；新信源/途径按名解析 get-or-create，新信源待确认）。12 tests 全绿，覆盖率 100%。

阶段 4 完成（TDD）：agents/collector.py Collector 最简归因（人工提交路径 → LLM 归因 Source/Outlet → 组装五要素线索提案）+ agents/llm.py（openai+instructor，DeepSeek 起步，env 配置切换）+ ledger LlmCall 计量表（智能体/对象/token/时间/模型，迁移 dbd4fff9cbbd）；计量即时入账与提案成败解耦。LLM 测试全程 mock，17 tests 全绿、覆盖率 100%。

阶段 5 完成（TDD）：web/submissions.py 录入素材页（媒介下拉封闭集合排除互联网、陈述文本框、提交→Collector→提案→落账 Lead、近期人工提交列表、驳回原因回显）+ web/deps.py 请求级会话与 LLM 注入 + Jinja2 模板；B008 按 FastAPI 惯用法豁免。22 tests 全绿、覆盖率 99%（仅 deps 胶水未覆盖，doc-08 口径说明）。

阶段 6 部分完成：干净环境一条命令重建已验证（down -v → build → up：启动即迁移、媒介/载体 seed 就位、healthz 200、录入素材页渲染、内部会议在下拉中）。待办：CI 实跑（需 push）、AC#1 真实 LLM 走查（需 LLM_API_KEY）、AC 措辞裁决（会议讨论 vs 术语表内部会议）。

裁决落账：媒介定名「会议讨论」（术语表 §六已同步，seed/code 改 meeting_discussion，AC 措辞无需再改）。AC#1 真实 LLM 走查通过（DeepSeek 归因信源 W 公司+途径渠道大会现场，落账 lead 待确认，计量 608+120 tokens）；AC#2 走查通过（双缺失拦截、无提案）。覆盖率可见性：本地 pytest 即生成 htmlcov/，CI 上传 coverage artifact。
<!-- SECTION:NOTES:END -->
