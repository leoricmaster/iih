---
id: IIH-02
title: 多载体素材录入
status: To Do
assignee: []
created_date: '2026-09-15 09:17'
updated_date: '2026-09-15 09:20'
labels:
  - product
  - pipeline
  - ui
milestone: m-1
dependencies: []
references:
  - doc-06 §3
  - doc-07 §2.3
  - IIH-01.01
  - DRAFT-08
priority: high
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要把会议录音、截图、文档等多种形态的素材直接送进流水线，以便不再只能靠文字纪要录入线下情报，让不同形态的一手素材都能成为情报源。

现状：m-0 仅支持文字纪要录入（IIH-01.01），运维方拿到录音、图片、文档时只能自己先转写/摘录成文字再提交——既丢原文形态（溯源五要素里的「载体」丢失），又增加人工负担。

范围：录音（ASR 转写）、图片（OCR 提取）、文档（正文解析）三种附件载体管线，复用 IIH-01.01 的归因与状态机落账通路；原文快照按载体类型存原始文件；抽取的陈述经审查/核实走全流水线。

范围外：视频载体、音视频转录的人工校对界面、附件批量上传优化。

关联：IIH-01.01（文字纪要录入奠基）、doc-06 §3（采集智能体最简归因）、doc-07 §2.3（录入素材页）、DRAFT-08（素材一等实体与派生链）。
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->
