#!/usr/bin/env bash
# 拆分与推送脚本
#
# 用法：
#   ./scripts/split_repos.sh split     # 生成五个独立仓库到 ../zg-tsp-repos/
#   ./scripts/split_repos.sh push      # 推送到各仓库的 origin（需先配置 remote）
#   ./scripts/split_repos.sh status    # 查看各仓库状态
#
# 说明：拆分用 git subtree split 保留完整提交历史；
# 分支根目录即模块根目录，clone 后无需调整路径。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/../zg-tsp-repos"
BRANCH_PREFIX="split/"

MODULES=(zg-tsp-server zg-tsp-web zg-tsp-ios zg-tsp-android zg-tsp-docs)

cmd_split() {
  echo "==> 拆分到 ${OUT}"
  mkdir -p "${OUT}"
  for m in "${MODULES[@]}"; do
    echo "--- ${m} ---"
    git -C "${ROOT}" subtree split --prefix="${m}" -b "${BRANCH_PREFIX}${m}"
    rm -rf "${OUT}/${m}"
    git -C "${ROOT}" clone -q --branch "${BRANCH_PREFIX}${m}" \
        --single-branch "${ROOT}" "${OUT}/${m}"
    git -C "${OUT}/${m}" remote remove origin
    git -C "${OUT}/${m}" branch -m main
    echo "    ✓ $(git -C "${OUT}/${m}" rev-list --count HEAD) 次提交"
  done
  echo
  echo "完成。各仓库位于 ${OUT}"
  echo "推送前请先为每个仓库配置 remote："
  echo "  git -C ${OUT}/zg-tsp-server remote add origin <url>"
}

cmd_push() {
  for m in "${MODULES[@]}"; do
    dir="${OUT}/${m}"
    if [ ! -d "${dir}/.git" ]; then
      echo "跳过 ${m}（未找到本地仓库）"
      continue
    fi
    if ! git -C "${dir}" remote get-url origin >/dev/null 2>&1; then
      echo "跳过 ${m}（未配置 origin）"
      continue
    fi
    echo "==> 推送 ${m}"
    git -C "${dir}" push -u origin main
  done
}

cmd_status() {
  for m in "${MODULES[@]}"; do
    dir="${OUT}/${m}"
    if [ -d "${dir}/.git" ]; then
      printf "%-16s 分支=%-6s 提交=%-4s remote=%s\n" \
        "${m}" \
        "$(git -C "${dir}" branch --show-current)" \
        "$(git -C "${dir}" rev-list --count HEAD)" \
        "$(git -C "${dir}" remote get-url origin 2>/dev/null || echo '未配置')"
    else
      printf "%-16s 未检出\n" "${m}"
    fi
  done
}

case "${1:-status}" in
  split)  cmd_split ;;
  push)   cmd_push ;;
  status) cmd_status ;;
  *) echo "用法：$0 {split|push|status}"; exit 1 ;;
esac
