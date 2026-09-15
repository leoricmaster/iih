---
id: IIH-05.01
title: 待确认信源确认闭环
status: In Progress
assignee:
  - '@lancer'
created_date: '2026-09-15 12:31'
updated_date: '2026-09-15 14:55'
labels:
  - product
dependencies: []
references:
  - decision-05
  - doc-04 §1
  - IIH-01.07
parent_task_id: IIH-05
priority: medium
type: feature
ordinal: 18002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要对人工录入归因产生的待确认信源逐一确认入池或拒绝，以便只有经我把关的信源进入信源库参与采集、画像与信用记账（decision-05 准入把关）。

现状：人工录入素材的溯源归因已能新建待确认信源（仅作记录，不入库、不建画像、不记账）；登记提案的记账层落账已支持确认入池（已确认态 + 初始信用档），但 Web 无确认入口——信源库、收件箱、条目详情、信源画像四处挂着「确认功能即将上线」占位。

范围：信源库对待确认信源的确认/拒绝入口（确认时给定初始信用档、可修正信源名与类型——撞既有已确认信源名即合并迁移；确认/合并旧名记为信源别名，归因解析按名或别名命中已确认信源，不重建待确认）；确认后入信源库、建画像、可被情报需求绑定与调度派单；拒绝留痕不入池；替换全部确认占位文案。

范围外：采集发现的新信源发现提案的确认（归池外自由探索单，确认入口复用本单）；确认后人工设档与反馈累计分归一（IIH-04.02）；无名/复合主体不该成为信源的归因把关（DRAFT-12）；归因提示词注入信源名单等判断层归一（后续）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 待确认信源 S（人工录入归因产生）When 消费方在信源库确认并给定初始信用档 Then S 进入信源库（已确认态）、建立画像、可被情报需求绑定与调度派单
- [ ] #2 Given 待确认信源 S When 消费方拒绝 Then S 不入信源库、留痕（拒绝记录可见），已归因到 S 的既有条目不受影响
- [ ] #3 Given 信源 S 尚未确认 When 调度器与记账运行 Then S 不参与派单、不建画像、不参与信用记账（decision-05 边界保持）
- [ ] #4 Given 待确认信源 S When 消费方确认时改名且新名与既有已确认信源 T 同名 Then S 并入 T（条目/转引链节点/途径迁移，同名途径复用）、S 行删除、信用档沿用 T；改名未撞名 Then 以新名入池
- [ ] #5 Given 已确认信源 T 带别名 a（确认改名/合并时自动产生）When 人工录入归因抽出 a Then 直接归因 T，不新建待确认信源；登记/改名撞别名一律驳回或并入
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [ ] #2 全部「确认功能即将上线」占位替换为确认入口（信源库/收件箱/条目详情/信源画像）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## 实现计划

### 设计抉择
1. 确认/拒绝走提案（SourceConfirmProposal / SourceRejectProposal，同 source_register 模式：无 provenance/formula_version），状态机唯一写账入口；消费方确认类比消费方登记（IIH-01.07 先例）。
2. 拒绝留痕 = Source.rejected_at（DateTime 可空，非新表）：拒绝时置时间戳，确认时清空；待确认列表仍列已拒绝条目（标「已拒绝·时间」pill），保留确认按钮——再次归因命中同名信源时无死区。
3. 确认必设初始信用档（A–F，默认 C），与种子登记同规（doc-04 §2.3 解死锁）。
4. UI：新建 _macros.html 确认/拒绝表单宏（初始档 select + 确认入信源库 + 拒绝），信源库/收件箱/信源画像三处复用；条目详情存疑提示改链接。next 参数回跳原页（白名单：/ 开头且非 //）。

### 阶段 1 · 提案契约（ledger/proposal.py）
- SourceConfirmPayload{source_id, initial_credit} + SourceConfirmProposal（source_confirm）
- SourceRejectPayload{source_id} + SourceRejectProposal（source_reject）

### 阶段 2 · 模型与迁移
- Source.rejected_at: DateTime(timezone=True) 可空
- alembic 迁移 add column

### 阶段 3 · 状态机（ledger/state_machine.py）
- _execute_source_confirm：校验存在 + confirmed=False 前置 + 档必填∈ABCDEF + 依据非空；落账 confirmed=True、credit、rejected_at=None
- _execute_source_reject：校验存在 + confirmed=False 前置 + 依据非空；落账 rejected_at=now

### 阶段 4 · Web（web/sources.py + 模板）
- POST /sources/{id}/confirm（initial_credit, next）、POST /sources/{id}/reject（next）→ 提案 → flash 回跳
- sources.html：待确认区每行确认/拒绝表单 + 已拒绝 pill，删「确认功能即将上线」；sources_page 加 flash
- inbox.html：待确认信源区同上（复用宏），删占位
- source_detail.html：未确认分支整页占位 → 确认/拒绝入口 + decision-05 说明
- item_detail.html:62 存疑提示「确认功能即将上线」→ 去信源画像确认链接
- 占位替换 4 处（信源库/收件箱/条目详情/信源画像）；source_detail:84「画像功能即将上线」非确认占位，不在本单范围

### 阶段 5 · 测试（TDD）
- test_state_machine：confirm 落账（含清 rejected_at）/ 驳回（不存在、已确认、档缺失、档非法）/ reject 落账 / 驳回（不存在、已确认）/ confirm 后 IR 绑定放行（AC#1 可绑定）
- test_web：AC#1 端到端（表单确认 → 已确认列表 + DB credit + 可被 IR 绑定）/ AC#2（拒绝 → rejected_at 落账 + 留痕可见 + 既有条目不受影响）/ 占位替换 4 处 / 档非法回显
- AC#3 边界沿用既有测试（test_director::excludes_unconfirmed、test_credit::skips_unconfirmed、test_state_machine 自动拉取/IR 绑定拒未确认），不重测

### 阶段 6 · 文档与收尾
- doc-04 §1 信源行补「确认状态（待确认/已确认，拒绝留痕）」（DoD #9）
- 本地门禁（ruff/format/mypy/pytest-cov）+ docker compose 重建浏览器走查 AC#1/AC#2
- AC/DoD 勾选 + Final Summary
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
阶段 1-2 完成：proposal.py 新增 SourceConfirmPayload/Proposal（source_confirm）、SourceRejectPayload/Proposal（source_reject），均无 provenance/formula_version（消费方准入决策非情报产出，同 source_register 先例）；Source.rejected_at 可空时间戳（拒绝留痕，确认时清空、非终态）+ 迁移 h7a8b9c0d1e2。

阶段 3 完成：状态机 _execute_source_confirm（校验存在 + confirmed=False 前置 + 档必填∈ABCDEF + 依据非空；落账 confirmed=True + credit + rejected_at=None）/ _execute_source_reject（前置同前；落账 rejected_at=now、confirmed 保持 False）。已归因条目不受影响——仍指向该信源，不记账由 confirmed 边界保持。

阶段 4 完成：web/sources.py 新增 POST /sources/{id}/confirm|reject（next 回跳白名单：/ 开头且非 //，防开放重定向；redirect_with_flash param=err 复用）；sources_page 加 flash/err；新建 _macros.html 确认/拒绝表单宏（初始档 select 默认 C + 确认入信源库 + 拒绝），信源库/收件箱/信源画像三处复用；条目详情存疑提示改「去确认 ↗」链接。四处「确认功能即将上线」占位全部替换；source_detail「画像功能即将上线」非确认占位，不在本单范围。

阶段 5 完成：test_state_machine 新增 7 用例（确认落账含清 rejected_at / 确认后 IR 绑定放行 / 确认驳回不存在+已确认+档缺失+档非法 / 拒绝落账 / 拒后再确认无死区 / 拒绝驳回）；test_web 新增 5 用例（AC#1 端到端确认→入池+画像开放+IR 绑定 / AC#2 拒绝留痕+条目不受影响 / DoD#2 四处占位替换 / 档非法回显 / next 白名单）。AC#3 边界沿用既有测试（test_director 排除未确认、test_credit 跳过未确认记账、test_state_machine 自动拉取与 IR 绑定拒未确认）。本地门禁绿：ruff check/format 通过、mypy src 40 文件无问题、pytest 303 passed 覆盖 93%。doc-04 §1 信源行补确认状态、§2.3 补确认设档规则。

走查反馈轮（用户四点）：①信源库布局对调——主表上、待确认区下；②无名/复合主体不该成为信源（如「王总、李总（公司管理层）」）——归因/转录环节问题，范围外，已开 DRAFT-12 留痕；③按钮精简——「确认」「拒绝」并列单行（原「确认入信源库」+独立拒绝表单布局丑）；④确认时支持修正信源名：SourceConfirmPayload 加 name 字段，状态机三分支——未改名直接入池 / 改名未撞名以新名入池 / 撞既有已确认信源名并入该信源（_merge_into_confirmed：条目+转引链节点+途径迁移，同名途径复用目标既有途径且待确认途径行删除——不删会 null 外键违约，条目/节点改指既有途径；信用档沿用目标；待确认行删除）；撞另一待确认信源名驳回「先处理该信源」。任务范围与 AC#4 已更新。

反馈轮验证：本地门禁绿（ruff/format/mypy/pytest 308 passed 覆盖 93%，新增 3 状态机用例 + 2 Web 用例）；Docker 重建走查——布局对调生效（主表 line61 前、待确认 line77 后）、四占位 0、改名确认（走查改名信源→走查改名后信源 B 档）、合并（走查合并信源→三一集团：条目 35 与节点迁至 source_id=1、待确认行删除、flash 已并入既有信源）；走查数据已清理，运行库还原为 4 信源原状。doc-04 §2.3 补改名/合并语义。

交互返工轮（用户反馈：信源名重复出现两次、初始档与按钮布局丑）：采纳「默认可编辑」方案——信源名只出现一次，行首即编辑框（.srcname 透明边框+加粗，hover 显框、聚焦蓝框，静态观感/点击即编辑）；新增 .srcrow 系列样式（app.css），初始档 select 摆脱全局 width:100% 改紧凑右置（width:auto;padding:2px 6px），Ⓘ 图标化；确认/拒绝同排右侧垂直居中；类型/状态 pill 收进行内。宏签名加 type_label 参数，整行（名+pill+操作）由宏统一渲染，三处调用点简化。自验收：结构（名仅一次）、改名确认端到端、76 web 用例 + ruff/format 绿；Docker 重建后走查通过。走查中观察到用户已实际操作：三一→三一集团合并成功、王总李总已拒绝留痕——真实数据验证合并与拒绝路径。

第六轮验收整改（别名 + 类型修正 + 布局）：
- 采纳别名机制（用户裁决，原 DRAFT-13 撤销并入本需求）：确认改名/并入/画像页改名时旧名留档为 SourceAlias（全局唯一）；MANUAL/AUTOMATED 归因解析按 名→别名 归入已确认信源，不再重复产生待确认行；登记/确认/画像改名撞别名均驳回并指明归属。
- 确认时类型可修正（下拉带当前类型选中）；并入路径沿用目标信源类型。
- 布局：信源名行内即编辑定宽 200px、类型/初始档/按钮对齐单行；SOURCE_TYPE_LABELS 收敛到 context.py 共享。
- 迁移 k9b0c1d2e3f4（source_alias 表）已应用于 docker 库；浏览器走查通过（合并路径信用档沿用、非合并改名留别名、画像页别名 pill 可见、不存在兜底）；临时数据已清理。
- 门禁：ruff/format/mypy 绿，pytest 315 passed。

第七轮验收整改（拒绝出队 + 别名展示）：
- 拒绝即出队（用户裁决）：待确认区过滤 rejected_at IS NULL（信源库 + 收件箱两处）；归因解析命中已拒绝信源时清 rejected_at 重捞入队，复用原行不新建。
- 拒绝历史事件表 source_rejection（迁移 l1c2d3e4f5a6）：每次拒绝追加留痕；重捞行内「曾拒 ×N」pill（title 带最近拒绝时间）。
- 信源库列表主体名后内联别名 pill（仅有别名时出现）。
- 布局返工根因：全局 input[type=text]{width:100%} 优先级压过 .srcname → 输入框满宽换行；改 input.srcname 等特异度选择器（160px）+ 单表单布局（拒绝经 button formaction），确认/拒绝恒并列。自查两页 × 1280/960 四截图通过。
- 门禁：ruff/format/mypy 绿，pytest 319 passed；docker 走查（拒绝→出队→重捞→曾拒 pill、别名 pill）通过，临时数据已清理。
<!-- SECTION:NOTES:END -->
