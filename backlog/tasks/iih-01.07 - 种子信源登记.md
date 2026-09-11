---
id: IIH-01.07
title: 种子信源登记
status: To Do
assignee: []
created_date: '2026-09-11 03:09'
updated_date: '2026-09-11 08:38'
labels:
  - product
  - ui
dependencies:
  - IIH-01.01
references:
  - doc-04
  - doc-07 §2.1/§3
  - prototype/index.html
parent_task_id: IIH-01
type: feature
ordinal: 4000
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
