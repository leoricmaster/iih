---
id: IIH-07.01
title: 长期文档重梳
status: Done
assignee:
  - '@lancer'
created_date: '2026-09-18 02:07'
updated_date: '2026-09-18 02:42'
labels:
  - docs
dependencies: []
references:
  - backlog/docs/doc-02 - 领域模型-Domain-Model.md
  - backlog/docs/doc-03 - 术语表-Glossary.md
  - backlog/docs/doc-04 - 数据设计-Data-Design.md
  - backlog/docs/doc-05 - 技术架构-Technical-Architecture.md
  - backlog/docs/doc-06 - 智能体规约-Agent-Specification.md
  - backlog/docs/doc-07 - 信息架构-Information-Architecture.md
  - backlog/docs/doc-08 - 完成定义-Definition-of-Done.md
parent_task_id: IIH-07
type: chore
ordinal: 26002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
长期文档随迭代补丁式更新累积三类病灶，可读性与一致性劣化，需一次整体重梳（重写而非增补）。全文评审于 2026-09-18，证据如下。

病灶一 · 一条规则多个正本，已实际腐化：
- 反馈类型计数不一致：doc-04 §1 与 doc-05 §6 写「六类型」，doc-02 §6 / doc-03 / doc-07 均为七类型。
- doc-04 §2.3 引「doc-02 §4.1」（情报需求状态机），按语义应为 §4.3（存疑回流属情报条目状态机）。
- 复述重灾区：反馈路由（4 处）、拆解-合成骨架（4 处）、实体层边界（2 处）、CI 工具链（doc-05 §8 与 doc-08 各一遍）。

病灶二 · 过程性内容渗入设计文档：
- 任务/draft ID 9 处：IIH-03.01、IIH-05.02、IIH-06.01（4 处）、IIH-06.02、DRAFT-08。
- 实现细节：difflib 相似度 0.7、temperature=0、Source(confirmed=False) 伪代码、「任务暂不落账、内存对象即时消费」进度注记。
- 修订注记混入术语定义：「decision-05 修订 2；途径 Outlet 术语退役」。

病灶三 · 巨型补丁段：doc-02 §3 实体层段、doc-04 §2.3 信用档生命周期段（各约 600 字 5+ 主题）、doc-06 §3 探索任务算法链。

重梳方向（经用户裁决 2026-09-18）：
1. 一条规则一个单一事实来源，其余处一行指针；反馈路由唯一正本 doc-02 §6。
2. 信用档生命周期与确认制流程自 doc-04 搬 doc-02（领域规则）；doc-04 §2 只留公式与分档表。
3. doc-03 瘦身为纯术语表（术语/English/一句话），「如何选择/如何联动/易混点」机制讲解归 doc-02。
4. doc-06 §7 并入 §6 或删除。
5. 工具选型记录（trafilatura / Tavily / Playwright）自 doc-05 §4 抽出独立成节（默认裁决；如改下沉代码注释须用户确认）。
6. 设计文档净空三不——任务 ID、实现参数与库名、修订与进度注记不入 doc-02~07 正文（decision-XX 溯源引用保留）——落 CLAUDE.md。
7. doc-08 DoD #9 措辞改为「已更新沉淀，融入既有结构，不追加补丁句」。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 反馈七类型路由唯一正本在 doc-02 §6；其余文档出现处均为指针或本层独有信息（doc-07 仅「入口 × 开放类型」表）
- [x] #2 doc-02~07 正文零任务/draft ID、零实现库名与参数、零修订与进度注记（decision-XX 引用除外）
- [x] #3 超约 150 字且含 3 个以上主题的段落重组为小节或表格
- [x] #4 全量交叉引用核对通过：章节引用指向正确，类型计数等数值全文一致
- [x] #5 信用档生命周期与确认制正本在 doc-02；doc-04 §2 仅存公式与分档表
- [x] #6 CLAUDE.md 含净空纪律；doc-08 DoD #9 措辞已更新
- [x] #7 两处已发现腐化（六/七类型不一致 ×2、§4.1 错引）消除
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
- [x] #2 重梳后全部文档经用户通读验收
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 先重写 doc-02（多数规则的新家）：信用档生命周期与确认制流程自 doc-04 搬入并成节；§3 实体层巨段拆小节；吸收 doc-03 机制讲解块；确认反馈路由正本（§6）。
2. doc-03 瘦身为纯术语表（术语/English/一句话/示例），机制块（如何选择/如何联动/易混点）改为指针指向 doc-02 对应节；定义去修订注记。
3. doc-04：§2.3 流程性内容搬走后仅存公式与分档表；反馈行「六类型」改七类型；修 §4.1 错引。
4. doc-05：§4 内嵌抓取/检索选型抽出为独立「工具层选型记录」节；§6 交互流压缩复述（保留提案链视角）；§8 与 doc-08 的 CI 工具链收敛单一正本；「六类型」改七类型。
5. doc-06：探索任务算法链压缩为契约级描述；「任务暂不落账」进度注记移出（入代码/任务留痕）；§7 并入 §6；清伪代码与 temperature。
6. doc-07：清任务 ID 与「通路反转」过程注记；§5 保留「入口 × 开放类型」独有表。
7. doc-08 DoD #9 措辞更新；CLAUDE.md 增净空三不一言。
8. 全量交叉引用核对：grep 验证净空（IIH-/DRAFT-/difflib/temperature/六类型），章节号指向逐一核对。
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
验证证据（2026-09-18）：
- 净空：grep IIH-/DRAFT-/difflib/temperature/TAVILY/confirmed= 于 doc-02~07 零命中；「六类型」全 docs 零命中，七类型 doc-02（路由表正本）/doc-03/doc-04/doc-07 一致。
- 引用核对：全部跨文档 §引用逐一对照（含书名号格式），doc-02 重写保住 §4.1~4.4/§5/§6 节号，外部引用零断链。
- 正本收敛：反馈路由唯一正本 doc-02 §6（doc-03 定义行、doc-05/doc-07 指针）；信用档生命周期与准入正本 doc-02 §7（doc-04 §2.3 仅存公式与分档）；工具选型独立为 doc-05 §8。
- 体系完好：backlog doc list 八篇齐全；diff -142/+125。
- DoD #7 豁免依据：文档级调整不落 decision（既有裁决惯例）。
待用户通读验收（特有 DoD #2）后提交并关单。
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
重写 doc-02~08 与 CLAUDE.md 净空纪律：一条规则一个正本（反馈路由 doc-02 §6、信源准入与信用档生命周期 doc-02 §7、工具选型 doc-05 §8）、设计文档净空（任务 ID/实现参数/修订注记零残留，grep 验证）、三处巨段拆解、doc-03 瘦身 196→136 行、六/七类型与 §4.1 错引两处腐化修复、全量交叉引用零断链。用户通读验收通过；提交 55f1ea7（doc 正文，CI 绿）与 6c30b28（CLAUDE.md 规则）。
<!-- SECTION:FINAL_SUMMARY:END -->
