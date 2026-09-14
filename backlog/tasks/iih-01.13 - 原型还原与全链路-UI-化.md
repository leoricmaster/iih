---
id: IIH-01.13
title: 原型还原与全链路 UI 化
status: In Progress
assignee: []
created_date: '2026-09-14 12:16'
updated_date: '2026-09-14 14:30'
labels:
  - product
  - web
milestone: m-0
dependencies: []
references:
  - doc-07
  - prototype/index.html
  - doc-02 §4.1
parent_task_id: IIH-01
type: chore
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
把既有流水线全能力经浏览器可达，按 doc-07 §3 还原原型，支撑 IIH-01 全程浏览器验收。

范围：
1. 全站壳：三组导航（消费/探究/管理，未开通项置灰）、收件箱为首页、「录入素材」全局按钮。
2. 六页面：收件箱、情报条目列表+详情（筛选检索、核查深区折叠：转引链穿透/评级历史/反馈记录/独立信源计数/元数据）、情报需求列表+详情（全生命周期、规格微调、命中条目）、信源库+信源画像、录入素材。
3. 流水线 UI 化：抽取 run_round、后台自动循环（可配可关）、「立即运行一轮」按钮。

范围外：探究组页面（研究课题/命题/图谱）、推送通道、分发记录/警报、附件上传（IIH-01.09–11）、调度节奏配置。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 全程浏览器闭环可达：登记种子信源 → 建需求并激活 → 触发采集 → 收件箱出现带二维评级与溯源的已核实条目 → 反馈后信源画像信用变化可见
- [ ] #2 全站壳与六页面符合原型版式（doc-07 §3）
- [ ] #3 情报需求全生命周期经页面可用：新建（草稿）/激活/暂停/恢复/关闭、规格微调、命中条目可见
- [ ] #4 流水线经页面触发与观测：「立即运行一轮」回显采集/审查/核实计数；后台循环按配置间隔运行（0=关闭）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 页面走查以 prototype/index.html 为对照基准，偏差在 comment 留痕
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## 实现计划

1. **状态机补全（情报需求迁移）**：proposal.py 增 IntelligenceRequirementPausePayload/Proposal、ResumePayload/Proposal、ClosePayload/Proposal；state_machine.py 增三迁移（Active→Paused、Paused→Active、Active|Paused→Closed，校验前置态），复用 Register/Activate 落账模式。
2. **流水线核心抽取**：新建 src/iih/pipeline.py：run_pipeline_round(settings, session_factory, llm) → dict（采集 new/appended/skipped/failed + 审查 passed/rejected + 核实 verified/undetermined/failed），从 cli/collect.py、cli/review.py、cli/verify.py 抽核心循环（CLI 改为薄包装，打印 summary）。
3. **后台循环**：config.py 增 pipeline_interval_seconds（env IIH_PIPELINE_INTERVAL_SECONDS，默认 300，0=关）；app.py lifespan 起 asyncio task（间隔循环 + asyncio.Lock 防重叠，异常记日志续跑）。
4. **全站壳**：templates/base.html（侧栏三组导航 + 录入素材全局按钮 + 顶栏账户区）+ static/app.css（取原型样式）；未开通项（研究课题/命题/图谱）置灰标「未开通」；收件箱徽标 = 已核实未作废计数；mount StaticFiles。
5. **页面**（复用既有 POST：反馈、信源登记、素材提交）：
   - inbox.html：三类待办结构（待反馈=已核实未作废近似；警报/待确认信源空态保留），行内快捷反馈 + 「立即运行一轮」按钮（POST /pipeline/run → threadpool 同步执行 → 回跳带 summary flash）。
   - items 列表：/items?status=&mode=&q= 筛选（已核实起/线索/候选/存疑/作废/全部 × 全部/自动拉取/人工提交；q 检索陈述/信源名 ILIKE）。
   - item_detail：sticky（前后条目）+ hero（陈述/状态/评级/出处/事件时间/媒介载体/模式）+ 状态自适应主区（线索/候选=流水线进度；已核实=评级依据 N/R/公式版本；存疑=存疑说明；作废=事实错误理由）+ 反馈区（六类型+理由，事实错误必填）+ 折叠深区（元数据/独立信源计数/转引链穿透含归因标注/评级历史/反馈记录，details/summary 无 JS）。
   - requirements 列表+详情：分组列表；新建表单（Register 提案）；详情动作（激活/暂停/恢复/关闭，经新提案）；内容规格展示+激活态可改；命中条目（review_decisions.matched_requirement_id）。
   - sources 列表+画像：列表（主体/类型/途径/信用/历史反馈/状态）+ 登记表单（复用）；/sources/{id} 画像（信用档+credit_adjustments 历史+途径表+参与条目=转引链出现）。
   - submissions：原型版式重排（媒介选择+文字纪要+近期人工提交）。
6. **测试**：web 各页 GET/POST 路径（含筛选、需求动作迁移、画像页）；pipeline run_round 用 fake LLM 走全链；后台循环配置（0=不启动）与 app 集成冒烟。门禁同 CI（ruff/mypy src/pytest-cov≥80）。
7. **验收环境**：compose 重建镜像，配合本地夹具页（/tmp/iih-acceptance）走用户旅程。
<!-- SECTION:PLAN:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: Claude
created: 2026-09-14 12:54
---
走查偏差与裁决留痕（DoD#2）：
1. 登记表单新增「初始信用档」字段（原型无此字段）——decision-09：新信源初始档人工设，解「未设档→存疑→无反馈口→永不设档」死锁，冷启动闭环可达。
2. 详情页反馈表单门控按原型（仅已核实起开放反馈，doc-07 §5）；本里程碑无已分发/已消费态，以已核实近似。
3. 探究组（研究课题/命题/图谱）按用户裁决显示但禁用（置灰标未开通）。
4. 流水线触发按用户裁决：后台自动循环（默认 300s，PIPELINE_INTERVAL_SECONDS 可配，0=关闭）+「立即运行一轮」按钮。
验收环境已验证（真实 DeepSeek）：登记（B 档）→ 建需求并激活 → 立即运行一轮 → 收件箱 B2×独立信源×1 → 有效反馈 → 画像 +1/1.00/source_credit_v1。
---

author: user
created: 2026-09-14 13:18
---
验收偏差 #5（2026-09-14）：「立即运行一轮」后 flash 显示存疑 1，但收件箱只列已核实、无任何指向，用户找不到结果。根因链：①信源登记未设初始信用档（decision-09 字段默认不设）→ 核实 R 空 → 按设计判存疑；②收件箱无存疑指向。修复：收件箱加「待复核（存疑）」计数与链接。验收偏差 #6：已登记信源无补设信用档入口，且存疑条目无回流路径（反馈门控限已核实 → 首次反馈设档路径不可达，死路）。裁决（用户）：画像页补设/调整信用档（A–F，decision-09 同机制直接改档）+ 存疑条目详情「重新核实」按钮（存疑→候选→确定性重核，doc-02 §4.1「新证据」回流）。验收偏差 #7：情报需求激活后无法快速验证配置是否能抓到情报，须等下轮采集。裁决（用户）：需求详情加「配置自检」按钮——试采集预览不落账（逐途径抓取→抽取陈述→按本需求审查预判，结果回显）。
---

author: user
created: 2026-09-14 13:45
---
验收偏差 #8（2026-09-14）：decision-09「可不设」留空即触发信用死锁（未设档→存疑→反馈不开放→永不设档）。裁决（用户）：初始信用档登记必填（A–F，默认 C 中性），登记表单与画像页加悬浮提示解释档位含义（A≥8 … F<−8、+1/−2、180 天半衰期）；doc-04 §2.3 同步修订；decision-09 修订为必填。
---

created: 2026-09-14 14:09
---
偏差 #9（用户走查）：正式 Web 页面携带内部设计痕迹——模板文案大量出现 doc-XX §Y / decision-XX 章节引用及「后续里程碑开通/加厚」「通道一/二」「双通道」「冷启动」等开发用语，面向客户不妥。处置：9 个模板文案产品化（去内部引用，保留术语表领域术语与功能说明），信源库页 1 处错误提示同步清理；内部引用仅保留在代码注释与测试注释中（不渲染）。代码注释/docstring、落账 rationale（审计数据、页面不渲染）不在本次范围。
---
<!-- COMMENTS:END -->
