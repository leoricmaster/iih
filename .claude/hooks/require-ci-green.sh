#!/usr/bin/env bash
# DoD #3 门禁（doc-08）：backlog 任务标终态（Done/Completed）前，须满足——
#   1. 除 backlog/ 元数据外工作区无未提交改动（代码已入库）
#   2. HEAD 已推送至 origin/main
#   3. HEAD 对应的 GitHub Actions CI 结论为 success
# 不满足任一项即阻断（exit 2），原因回显给模型。
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty')

# 只拦截 backlog task edit 的终态设置（允许 rtk 前缀重写；不锚定，容复合命令）
grep -Eq 'backlog[[:space:]]+task[[:space:]]+edit' <<<"$cmd" || exit 0
grep -Eq -- '(-s|--status)[[:space:]]+["'\'']?(Done|Completed)' <<<"$cmd" || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 2

# 1. 未提交改动（backlog/ 元数据豁免——收尾提交在关任务之后）
# porcelain 行为「XY␣路径」；路径含非 ASCII/空格时被 C 转义引号包裹，豁免须容忍可选引号
dirty=$(git status --porcelain | grep -v -E '^.. ?"?backlog/' || true)
if [ -n "$dirty" ]; then
  echo "DoD#3 门禁：存在 backlog 之外的未提交改动——先提交并推送，CI 绿后再标终态。" >&2
  exit 2
fi

# 2. HEAD 须已推送
sha=$(git rev-parse HEAD)
remote=$(git rev-parse origin/main 2>/dev/null || true)
if [ -z "$remote" ] || [ "$sha" != "$remote" ]; then
  echo "DoD#3 门禁：HEAD（${sha:0:7}）未推送至 origin/main——推送并等 CI 绿后再标终态。" >&2
  exit 2
fi

# 3. HEAD 的 CI 须绿
conclusion=$(gh run list --commit "$sha" --json conclusion --limit 1 | jq -r '.[0].conclusion // empty')
if [ "$conclusion" != "success" ]; then
  echo "DoD#3 门禁：commit ${sha:0:7} 的 CI 未绿（当前：${conclusion:-运行中或无记录}）——等绿或修复后再标终态。" >&2
  exit 2
fi

exit 0
