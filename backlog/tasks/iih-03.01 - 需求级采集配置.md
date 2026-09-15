---
id: IIH-03.01
title: 需求级采集配置
status: In Progress
assignee:
  - '@claude'
created_date: '2026-09-15 07:46'
updated_date: '2026-09-15 10:03'
labels:
  - product
  - pipeline
dependencies: []
references:
  - doc-04 §1
  - doc-02 §4.1
  - IIH-01
  - IIH-01.13
parent_task_id: IIH-03
priority: medium
type: feature
ordinal: 16001
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为消费方，我想要为每个情报需求独立指定采集节奏、时效与覆盖的信源范围，以便按需求紧迫度差异化投入采集资源、控制负载与费用，并在需求列表一眼看见各需求的采集配置差异。

现状（m-0）：所有激活需求共享全局调度间隔、覆盖全部已确认信源、无时效边界——列表里每个需求这三项都是同一个值，看不出差异。

范围：
1. 需求可独立配置采集频率（可空=继承全局间隔）。
2. 需求可独立配置事件时效边界（可空=不限，如「一周内」），审查据此否决过期线索。
3. 需求可独立配置生效窗口（起止日期，可空=常驻），到期自动关闭。
4. 需求可独立绑定关注的信源范围（可空=全部已确认信源；只能绑定已确认信源）。信源绑定只影响自动拉取派单——人工录入不受绑定限制，避免扼杀其引入新信源的价值。
5. 调度器按各需求独立参数分发采集任务，取代全局间隔 × 全激活需求笛卡尔积共用模式。
6. 情报需求列表与详情页展示四项配置，列表可一览差异。

范围外：「过期」反馈驱动配置调整的学习通路（DRAFT-10）；池外自由探索；多途径编排优化；调度成本核算仪表盘。

关联：doc-04 §1（情报需求字段含生效窗口）、doc-02 §4.1（需求状态机）、decision-05（待确认信源不入正式池）；IIH-01 范围外明列「调度节奏」、IIH-01.13 第六轮验收讨论留痕——三维度 m-0 全为常量、列表加列信息增益为零，差异化待本单落地。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 消费方为需求 A 配置频率 1h、需求 B 频率 24h When 调度器运行 Then A、B 按各自频率独立采集，互不干扰
- [ ] #2 Given 消费方为需求 A 绑定信源 [S1, S2]、需求 B 不绑定（=全部）When 调度器运行 Then A 仅派单到 S1/S2 的互联网途径，B 派单到全部已确认信源的互联网途径；人工录入无论归因信源是否在绑定内，都按内容规格正常匹配
- [ ] #3 Given 消费方为需求 A 配置事件时效「一周内」When 审查执行 Then 事件时间早于时效边界的线索被否决（不相关），不入候选
- [ ] #4 Given 消费方为需求 A 配置生效窗口至 2026-12-31 When 调度器运行至 2026-12-31 后 Then 需求 A 自动从激活转为关闭
- [ ] #5 Given 多个需求各自配置不同 When 消费方打开情报需求列表 Then 一眼可见各需求在频率、时效、来源、生效窗口四项上的差异
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 工具函数 parse_duration_to_seconds（Nh/Nd/Nw/Nm） 2. 模型字段+迁移（频率/时效/生效起止/last_collected_at + M-N 关联表） 3. Register payload 扩展与状态机校验 4. Director 调度差异化（到期关闭+due 过滤+信源绑定过滤） 5. Pipeline 更新 last_collected_at 6. Reviewer 时效否决 7. Web UI 列表四列+详情配置行+编辑表单+新建表单+配置更新端点 8. CLI ir-create 可选参数 9. 种子数据示例配置 10. 文档同步 doc-02/doc-04 11. 测试覆盖 12. 本地门禁与 Docker 重建
<!-- SECTION:PLAN:END -->
