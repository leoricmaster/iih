# IIH 智能情报中心

多智能体情报生产与研判系统：五类智能体（定向、采集、审查、核实、分析）承担情报循环的语义判断，确定性记账层负责状态机、信用计算、溯源与分发——**判断归智能体，记账归确定性系统**。产出带溯源与二维评级的情报条目、可翻案的命题结论，以及跨课题沉淀的实体底座；反馈回流信用与配置，使用越多系统越准。

## 文档

| 文档 | 内容 |
|---|---|
| [doc-01 立项文档](backlog/docs/doc-01%20-%20立项文档-Charter.md) | 为什么做、做什么、不做什么 |
| [doc-02 领域模型](backlog/docs/doc-02%20-%20领域模型-Domain-Model.md) | 概念与关系全景 |
| [doc-03 术语表](backlog/docs/doc-03%20-%20术语表-Glossary.md) | 领域术语单一事实来源（English 列即代码命名标准） |
| [doc-04 数据设计](backlog/docs/doc-04%20-%20数据设计-Data-Design.md) | 数据结构 |
| [doc-05 技术架构](backlog/docs/doc-05%20-%20技术架构-Technical-Architecture.md) | 三层架构落地：C4、提案契约、交互流 |
| [doc-06 智能体规约](backlog/docs/doc-06%20-%20智能体规约-Agent-Specification.md) | 五类智能体契约：输入、职责、输出、工具 |
| [doc-07 信息架构](backlog/docs/doc-07%20-%20信息架构-Information-Architecture.md) | 消费方侧页面、动线与反馈时机 |
| [doc-08 完成定义](backlog/docs/doc-08%20-%20完成定义-Definition-of-Done.md) | 通用 DoD 单一事实来源 |

需求与任务管理在 `backlog/`（Backlog.md），决策记录在 `backlog/decisions/`。

## 运行

依赖 Docker（Postgres 17、MinIO）；LLM 走 OpenAI 兼容端点，起步 DeepSeek。

```bash
cp .env.example .env    # 填 LLM_API_KEY；听悟 ASR、Tavily 为可选项，留空即关闭
docker compose up --build
```

启动即自动执行数据库迁移，服务在 http://localhost:8000。

本地开发：

```bash
uv sync
alembic upgrade head    # 需 .env 指向可用 Postgres（默认 compose 暴露的 localhost:5432）
uvicorn iih.web.app:app --reload
uv run pytest
```

部署运维命令走 CLI，不进 UI：`uv run python -m iih.cli`（子命令：collect / ir / review / seed / verify）。
