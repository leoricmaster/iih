---
id: IIH-07
title: 别名管理：删别名能力 + 改名留档规则修订
status: To Do
assignee:
  - '@zhangyunfeng'
created_date: '2026-09-17 07:17'
updated_date: '2026-09-17 07:19'
labels:
  - product
dependencies: []
references:
  - doc-04 §2.3
  - doc-03 别名
  - doc-07 信源画像
  - decision-05
type: feature
ordinal: 23002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
IIH-06.01 验收发现别名污染坑：信源名 A→B 改名（待确认确认改名 / 并入既有信源 / 画像页改名）时，系统按 doc-04 §2.3 规则自动把旧名 A 留档为别名，但 A 往往是 LLM 产出的脏名（如「新华网（新华社记者杨有宗，转载于中国科技网）」「weidn（据公开资料整理）」）——留档为别名污染别名表，且按别名归一规则可能捕获后续脏名。

本任务根治别名污染：
①画像页加「删别名」能力（状态机加 SourceAliasDelete 提案 + 留痕，按「无溯源不落账」原则）。
②修订 doc-04 §2.3 改名留档规则：确认改名 / 并入 / 画像页改名不再自动留档旧名为别名；别名改为「用户主动声明」语义（画像页支持加 / 删，归因解析按名→别名归入不变）。
③采纳 IIH-06.01 验收用户裁决：不开新 decision（adr-08），直接修订 doc-04 §2.3 与相关文档（doc-03 别名定义、doc-07 画像页信息架构、decision-05 若涉及）。
④清掉存量脏别名（手工 SQL 已删 source_alias id=5「新华网...」；weidn 那条待本任务一并清）。

留档规则修订涉及归因解析路径——归因产出已登记信源名或别名即归入，不再产生待确认行；改名不留档不影响此路径（已确认信源改名后，旧名不再被归因捕获，但 LLM 极少产出已确认信源的旧名，且即便发生也产生待确认行经人工并入处理）。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
