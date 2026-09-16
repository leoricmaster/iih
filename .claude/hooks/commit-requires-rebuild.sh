#!/usr/bin/env bash
# 提交门禁：若改动含部署路径，须先重建 web-app 容器并生效（stamp 须新于改动 mtime）
# 简化版：不自动重建，强制我显式跑 docker compose up -d --build web-app
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty')
grep -Eq 'git[[:space:]]+commit' <<<"$cmd" || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 2

# 暂存区与未暂存的改动里，是否含部署路径
changed=$(git status --porcelain | grep -E ' (src/|alembic/|pyproject\.toml|uv\.lock|Dockerfile|docker-compose\.yml)' || true)
[ -n "$changed" ] || exit 0  # 没碰部署路径，放行

# 容器没在跑：环境可能未起，放行让正常流程处理
docker compose ps web-app --format json 2>/dev/null | jq -e '.State == "running"' >/dev/null 2>&1 || exit 0

stamp_file=.claude/.web-rebuild-stamp

# stamp 须存在
[ -f "$stamp_file" ] || {
  echo "提交门禁：改动含部署路径（src/、alembic/、pyproject.toml、uv.lock、Dockerfile、docker-compose.yml），但容器从未重建——请先 docker compose up -d --build web-app，等健康后再提交。" >&2
  exit 2
}

stamp=$(cat "$stamp_file")

# 逐个比对改动文件 mtime 与 stamp
while IFS= read -r line; do
  path=$(echo "$line" | sed -E 's/^.. ?"?//; s/"$//')
  [ -n "$path" ] || continue
  mtime=$(stat -f '%m' "$path" 2>/dev/null || echo 0)
  if [ "$mtime" -gt "$stamp" ]; then
    echo "提交门禁：$path 在最近一次容器重建（$(date -r "$stamp" '+%H:%M:%S')）之后被改——请 docker compose up -d --build web-app，等健康后再提交。" >&2
    exit 2
  fi
done <<<"$changed"

exit 0