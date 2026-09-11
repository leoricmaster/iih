---
id: doc-08
title: 完成定义-Definition-of-Done
type: specification
created_date: '2026-09-11 01:37'
---

# 完成定义（Definition of Done）

通用 DoD 的单一事实来源。各任务 DoD 部分写「符合 doc-08 通用 DoD」+ 任务特有项（如有）。

## 通用 DoD

| # | 条目 | 适用条件 |
|---|------|----------|
| 1 | diff 只含任务相关改动，无顺手重构与格式噪音 | 全部 |
| 2 | 新增/修改代码行覆盖率 ≥80%，以 CI 覆盖率报告为准 | 涉及代码变更 |
| 3 | main 分支 CI 全量绿（含新增用例；ruff check、ruff format --check、mypy、pytest-cov 随 CI 生效） | 涉及代码变更 |
| 4 | 干净环境一条命令可重建：空 checkout → docker compose up → 服务可用 | 涉及基础设施/依赖变更 |
| 5 | 已知问题零静默遗留：修掉，或建 debt 标签任务登记 | 全部 |
| 6 | 术语与术语表（doc-03）一致，无同义词混用 | 涉及命名、文档、界面文案 |
| 7 | 架构级决策已落 backlog decision | 涉及架构决策 |
| 8 | 智能体产出附依据，无溯源不落账 | 涉及智能体产出 |
| 9 | 关闭任务时，若实现揭示长期文档（doc-01~doc-08）有更新必要，已更新沉淀 | 全部 |

## 豁免规则

- 适用条件不满足的条目视为满足（如纯调研任务于 #2/#3/#4）。
- 确实做不到的条目不得勾选：先在任务 comment 留痕豁免项与理由，经用户批准后方可关闭。
- CI 质量门禁（ruff、mypy、format 检查、pytest-cov）由首个奠基故事（IIH-03.01 素材人工录入，承载工程骨架与 CI 基线工作包）建立，此后 #2/#3 持续生效。

## 口径说明

- 覆盖率：起步用全仓口径（`pytest --cov --cov-fail-under=80`），代码库变大后切增量口径（diff-cover，对 origin/main 改动行统计）。
- 覆盖率是「关键路径已测」的代理指标：term-missing 报告中纯胶水（入口、配置）可依豁免规则处理。
