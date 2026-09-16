---
id: IIH-02.01
title: 录音附件管线
status: Done
assignee: []
created_date: '2026-09-11 09:24'
updated_date: '2026-09-16 12:08'
labels:
  - pipeline
  - ui
dependencies:
  - IIH-01.01
references:
  - doc-06 §3
  - doc-04 §1
  - doc-05 §3
  - prototype/index.html 录入素材页
parent_task_id: IIH-02
type: feature
ordinal: 19002
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
作为运维方，我想要上传录音附件经 ASR 转写产出线索，以便把会议/访谈录音送进流水线。

IIH-01.01 奠基阶段录入素材页只做文字载体；录音附件（ASR 转写）剥离承载，避免遗漏。录音载体经 ASR 管线转写为文字后，由采集智能体识别陈述、归因补记信源与途径、组装线索提案，与文字录入走同一条流水线（doc-06 §3）。

承载素材一等实体最小版：素材 = 不可变原件（对象存储）+ 载体/媒介/采集时间 + 处理状态机（PG 持久）；派生逐级记生产者（工具/智能体/人工）与产物，只追加；条目挂素材 + 派生引用，不内嵌快照；既有文字/网页路径不迁移。ASR 用阿里云通义听悟离线转写（OSS 中转、提交-轮询、说话人分离 + 时间戳）；上传即提交任务、既有循环轮询兜底；ASR 计量记派生行。

转写完成停「待标记」（门控）：近期素材展开转写稿，人工对发言人**全部**标记实名（转写稿实名替换，追加人工派生）后才进入抽取——标记完成转写稿才算完成，认不出的发言人填描述性称呼（信源确认时可改名）；抽取按发言人分段归因、逐人成源，新名信源经待确认闭环（decision-05）确认或拒绝，匿名标签不作信源（无实际意义）。
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given 运维方上传录音附件 When 经 ASR 转写为文字、采集智能体组装线索 Then 落账为「线索」态，溯源五要素齐备
- [ ] #2 Given 转写失败 When 管线处理 Then 不静默丢素材（落失败记录或重试），不产生半成品线索
- [ ] #3 Given 转写完成 When 发言人未全部标记实名 Then 素材停「待标记」不自动抽取，可查看转写稿；漏标拒绝（报缺谁），全部实名标记后继续
- [ ] #4 Given 发言人已标记实名 When 采集智能体抽取 Then 线索按发言人实名分别归因，实名信源进待确认队列（decision-05）
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 符合 doc-08 通用 DoD（完成定义与豁免规则）
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 术语与文档：术语表增素材 Material / 派生 Derivation（含派生链 Derivation Chain），同步 doc-02、doc-04（素材/派生表、条目挂链字段、溯源第三轨）
2. 建模与迁移：Material 表（载体/媒介/采集时间/原件对象键/文件名/音频时长/状态机 uploaded→transcribing→transcribed→extracting→completed ｜ transcribe_failed/extract_failed，失败原因 + 重试计数 + 听悟 task_id）；Derivation 表（素材/父级/生产者类型+标识/产物/时长——ASR 计量）；条目加可空 material_id + derivation_id；ProvenanceData 与状态机校验加第三轨
3. ASR 工具层：tools/asr.py 听悟适配器（OSS 中转上传 → 签名 URL → CreateTask（diarization 开）→ 轮询 → 下载结果 → 段落转写稿「[mm:ss] 发言人N：文本」；OSS 临时对象清理），参照 excavator 项目 asr_transcribe.py；环境变量凭据；依赖 alibabacloud_tingwu20230930 + oss2
4. 编排：上传端点（multipart 流式 → MinIO materials/ 内容寻址 → 建 Material 行 → 即时提交听悟任务）；循环兜底段（轮询 transcribing、重置卡死 claim、重试达上限转人工）；转写完成 → 停「待标记」（标记端点：全部实名替换转写稿追加人工派生，漏标拒绝）→ Collector 按发言人分段抽取 + 归因（标记实名逐人成源，匿名标签不作信源）→ 逐条提案落账 → 素材 completed（零陈述亦完成留痕）
5. Web UI：录入素材页附件上传（本故事仅 audio/*，图/文档拒收提示）+ 素材状态列表（待标记/转写中/完成/失败·重试，.flash toast）；待标记素材展开转写稿 + 发言人实名标记表单（同构 05.01 确认行），已完成素材可折叠查看转写稿
6. 测试与验收：ASR 适配器全 mock；状态机/待标记门控/逐发言人归因/失败重试/上传与标记端点集成测试；本地门禁绿 + docker compose build 后浏览器验收
<!-- SECTION:PLAN:END -->
