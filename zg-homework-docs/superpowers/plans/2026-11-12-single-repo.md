# 单一仓库化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `zg-tsp` 收敛为唯一开发源与唯一 git 仓库，删除「拆分为多个独立仓库」的机制与叙述，同时保留模块边界（独立依赖清单、零跨模块引用、独立打包）。

**Architecture:** 目录结构不变（`zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/`），删除 `scripts/split_repos.sh` 与四个 `split/*` 分支、`../zg-tsp-repos/` 三份独立检出。`scripts/dev.sh` 与 `scripts/init.sh` 去掉「多检出探测 + 差异统计」，根目录新增 `Makefile` 作为唯一入口。PRD 决策 6 改写为「单仓三模块目录，模块边界保留」。

**Tech Stack:** POSIX `sh`（dev.sh / init.sh）、GNU Make 3.81（macOS 自带）、Python 3.12（`.venv/bin/python`）、Markdown（PRD / README / CLAUDE.md）。

**Design spec:** `zg-tsp-docs/superpowers/specs/2026-11-12-single-repo-design.md`

## Global Constraints

以下约束对**每个任务**都生效（逐字摘自 spec）：

- **目录名不改**：`zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/` 三个目录名保持不变。
- **不重写 git 历史**：`main` 已含三个模块全部提交；`split/*` 分支本就是它的子树过滤。
- **不迁移微信小程序端**：代码留在 `~/WeChatProjects/HomeworkPoints`，本仓库不动它。
- **不引入新依赖**：根级入口只用系统自带 `make`，不引入根 `package.json` workspace 或根 `pyproject.toml`。
- **不改业务代码**：服务端 / Web 的接口契约、数据库结构、部署产物名与目标机路径全部不动。
- **`scripts/dev.sh` 与 `scripts/init.sh` 必须保持 POSIX `sh` 兼容**：不用数组、`[[ ]]`、进程替换、`$'...'`。
- **`dev.sh` 的三条既有语义不得丢失**：启动前不清 PID 文件、`start_bg` 用 `exec` 拿真实 pid、`stop` 兜底按端口清理。
- **模块边界保留**：依赖清单各自独立、源码零跨模块 import、各自可单独打包。
- **PRD 变更需同步客户端类型**：`zg-tsp-web/src/api/types.ts` 是 PRD 的手工副本。本次**不改任何接口**，故该文件无需变动。
- **临时测试脚本放 `docs/` 下**（根 `docs/` 被 gitignore，属本地联调资产，不入库）。

## 环境事实（已实测，勿重新假设）

- `/bin/sh` = bash 3.2 兼容模式；`sh -n` / `bash -n` / `zsh -n` 对现有 `dev.sh`、`init.sh` 均通过。
- 仓库根 `.venv/bin/python` 存在，`fastapi` + `uvicorn` 可用。
- MySQL 在 `127.0.0.1:3306`，`root/12345678`，已有库 `zg_tsp`。
- `zg-tsp-server/tests/` 被 gitignore，干净检出下无测试文件 —— `make test` 会空跑，不算失败。
- `make` 为 GNU Make 3.81（macOS 自带），支持 `$(shell ...)`、`.PHONY`、`:=`。
- `awk` 为 BSD awk（**不支持非贪婪 `.*?`**）—— Makefile 帮助解析必须用贪婪的 `":.*## "`。

---

## Task 1: 前置安全检查与基线冻结

**Files:**
- 无文件改动（只做检查 + 打 tag）

**Interfaces:**
- Consumes: 无
- Produces: git tag `archive/pre-merge-2026-11-12`（指向合并前的 `main`），供后续任务回滚；一份「三个独立检出无未提交改动」的确认结论。

- [ ] **Step 1: 确认 `../zg-tsp-repos/` 三个独立检出无未提交改动**

删除操作不可逆，先确认这���目录没有待保存的工作：

```bash
cd /Users/zg/PycharmProjects/zg-homework
for d in ../zg-homework-repos/*/; do
  echo "=== $d"
  git -C "$d" status --porcelain
  git -C "$d" log --oneline -1
done
```

Expected: 三段 `===` 之后各自**只有一行 commit 输出**，`status --porcelain` 无输出（即工作区干净）。

若任一目录的 `status --porcelain` **有输出**：**停下来**，把输出内容报告给用户，由用户决定是提交到该独立仓还是放弃。不要自行删除。

- [ ] **Step 2: 确认本仓库当前工作区状态**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git status --short
git log --oneline -1
```

Expected: `git log` 输出 `bfb8935 docs(spec): 修正设计文档 —— PRD 章节号纠错与验收标准改写补齐`。
`git status --short` 会列出若干 `??` 未跟踪文件（`zg-tsp-server/deploy/`、`zg-tsp-server/scripts/`、`zg-tsp-web/deploy/`、`zg-tsp-web/src/pages/parent/*.tsx`、`zg-tsp-docs/.wx-automation/` 等）——

**这些是本次任务范围外的既有工作，不提交、不删除、不修改。**

> 这是对 spec §4.1 第 1 步「提交当前工作区已有的未跟踪改动」的**有意偏离**：
> 这些改动与本次合并无关，且包含明显未完成的工作（如 `Homework.tsx` / `Reading.tsx` 家长端页面）
> 与工具产物（`zg-tsp-docs/.wx-automation/` 内含 `node_modules`）。把它们提交进主干是另一个决策，
> 应由用户单独决定。本任务只需**记录**它们的存在，确保合并过程不触碰。

- [ ] **Step 3: 打归档 tag**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git tag -a archive/pre-merge-2026-11-12 -m "单一仓库化合并前的基线存档"
git tag -l 'archive/*'
```

Expected: 输出 `archive/pre-merge-2026-11-12`。

- [ ] **Step 4: 确认 tag 可用**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git show --stat archive/pre-merge-2026-11-12 | head -5
```

Expected: 显示 commit `bfb8935` 的信息，无错误。

> 本任务不提交任何文件改动，故无 commit 步骤。**Task 12（破坏性删除）依赖本任务的 tag。**

---

## Task 2: 简化 `scripts/dev.sh` 为单仓库形态

**Files:**
- Modify: `scripts/dev.sh`（整文件重写）
- Create: `docs/test_dev_sh.sh`（本地冒烟测试，gitignored）

**Interfaces:**
- Consumes: 无
- Produces: `scripts/dev.sh` 仍接受 `REPOS_DIR` / `SERVER_PORT` / `WEB_PORT` / `API_TARGET` / `LOG_DIR` / `VENV_PY` 六个环境变量；子命令仍为 `start`（默认）/ `server` / `web` / `all` / `stop` / `status` / `logs`。新增行为：`REPOS_DIR` 指向不含 `zg-tsp-server` 或 `zg-tsp-web` 的目录时**立即退出并打印错误**（退出码 1），不再回退到其它探测位置。

- [ ] **Step 1: 写冒烟测试脚本 `docs/test_dev_sh.sh`**

```bash
#!/usr/bin/env bash
# dev.sh 单仓库形态的冒烟测试
#
# 覆盖：
#   1. 语法检查（sh / bash / zsh）
#   2. REPOS_DIR 无效时的报错与退出码
#   3. status 子命令
#   4. server 启停闭环（真实起进程，验端口与 PID 记录）
#
# 用法：bash docs/test_dev_sh.sh

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
FAILED=0

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAILED=1; }

echo "[1] 语法检查"
for shell in sh bash zsh; do
  if command -v "$shell" >/dev/null 2>&1; then
    if "$shell" -n scripts/dev.sh 2>/tmp/devsh_syntax.err; then
      pass "$shell -n scripts/dev.sh"
    else
      fail "$shell -n scripts/dev.sh: $(cat /tmp/devsh_syntax.err)"
    fi
  fi
done

echo
echo "[2] REPOS_DIR 无效应报错退出"
OUT=$(REPOS_DIR=/tmp/definitely-not-zg-homework ./scripts/dev.sh status 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  pass "无效 REPOS_DIR 退出码 $RC（非 0）"
else
  fail "无效 REPOS_DIR 退出码为 0，应为非 0"
fi
if printf '%s' "$OUT" | grep -q "代码目录无效"; then
  pass "错误信息包含「代码目录无效」"
else
  fail "错误信息未包含「代码目录无效」，实际输出：${OUT}"
fi

echo
echo "[3] status 子命令"
if ./scripts/dev.sh status >/tmp/devsh_status.out 2>&1; then
  pass "status 退出码 0"
else
  fail "status 退出码非 0"
fi
if grep -q "模块运行状态" /tmp/devsh_status.out; then
  pass "status 输出包含「模块运行状态」"
else
  fail "status 输出缺少「模块运行状态」：$(cat /tmp/devsh_status.out)"
fi

echo
echo "[4] server 启停闭环"
PORT="${TEST_PORT:-8123}"
WPORT="${TEST_WEB_PORT:-8124}"
# 用非常规端口，避免与开发中的 8000 / 5173 冲突。
if SERVER_PORT="$PORT" WEB_PORT="$WPORT" ./scripts/dev.sh server >/tmp/devsh_start.out 2>&1; then
  pass "server 启动退出码 0"
else
  fail "server 启动失败：$(cat /tmp/devsh_start.out)"
fi
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  pass "端口 ${PORT} 已监听"
else
  fail "端口 ${PORT} 未监听"
fi
if grep -q "^server " .dev-logs/dev.pids 2>/dev/null; then
  pass "PID 文件记录了 server 条目"
else
  fail "PID 文件缺少 server 条目：$(cat .dev-logs/dev.pids 2>/dev/null)"
fi
SERVER_PORT="$PORT" WEB_PORT="$WPORT" ./scripts/dev.sh stop >/tmp/devsh_stop.out 2>&1
sleep 1
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  fail "stop 后端口 ${PORT} 仍被占用"
else
  pass "stop 后端口 ${PORT} 已释放"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "全部通过"
else
  echo "存在失败项"
fi
exit "$FAILED"
```

- [ ] **Step 2: 运行冒烟测试，确认它在旧脚本上失败**

```bash
cd /Users/zg/PycharmProjects/zg-homework
bash docs/test_dev_sh.sh
```

Expected: **失败**。旧 `dev.sh` 在 `REPOS_DIR` 指向无效目录时会**静默回退**到自动探测的其它位置（`$ROOT`），照常打印报告并执行 `status`，**退出码为 0** —— 故第 [2] 项的「退出码应为非 0」与「信息应含『代码目录无效』」两条判定都会失败，脚本整体 `exit 1`。

这一步的目的是确认测试确实在检验新行为，而不是恒真。

- [ ] **Step 3: 重写 `scripts/dev.sh`**

用下列内容**整文件替换** `scripts/dev.sh`：

```sh
#!/bin/sh
# zg-homework 一键启动脚本
#
# 本仓库是**单一仓库**：服务端 / Web 端 / 文档同处一个检出。
# 脚本始终以本仓库为工作目录；如需指向别处检出（如 git worktree），
# 用 REPOS_DIR 环境变量显式指定。
#
# 本脚本刻意保持 POSIX sh 兼容：可用 sh / bash / zsh / dash 执行。
# 因此不使用 bash 专有语法（数组、< <(...) 进程替换、$'...'、[[ ]] 等）。
# 唯一非 POSIX 的依赖是 `local` 内建——sh/bash/zsh/dash 均支持，
# 但 macOS 自带的 ksh93u+ 不支持，在 ksh 下会报 "local: not found"。
#
# 用法：
#   ./scripts/dev.sh              # 启动 server + web（默认）
#   ./scripts/dev.sh server       # 只启动服务端
#   ./scripts/dev.sh web          # 只启动 Web 端
#   ./scripts/dev.sh all          # 启动全部
#   ./scripts/dev.sh stop         # 停止本脚本启动的所有进程
#   ./scripts/dev.sh status       # 查看各模块运行状态
#   ./scripts/dev.sh logs         # 跟随查看日志
#
# 环境变量：
#   REPOS_DIR   代码目录（默认脚本所在仓库；显式指定时必须含 zg-homework-server 与 zg-homework-web）
#   SERVER_PORT 服务端端口（默认 8000）
#   WEB_PORT    Web 端端口（默认 5173）
#   API_TARGET  Web 端代理指向的服务端地址（默认 http://127.0.0.1:$SERVER_PORT）
#   LOG_DIR     日志目录（默认 <仓库根>/.dev-logs）
#   VENV_PY     服务端 Python 解释器（默认 <仓库根>/.venv/bin/python，其次 python3）

set -eu

# $0 在 POSIX sh 下即为脚本路径，兼容 bash / dash / zsh。
#
# 一律用 `pwd -P` 取**物理路径**：默认的 `pwd` 返回逻辑路径（含符号链接），
# 当目录本身是软链接时，REPOS_DIR 与 ROOT 会因同一物理目录的两条路径
# 而不相等。
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"

# --- 定位代码目录 ---
# 默认就是本仓库。REPOS_DIR 只作**显式覆盖**（git worktree 等场景），
# 不再自动探测其它检出位置 —— 本仓库是唯一代码来源。
#
# 覆盖值无效时直接报错退出，不静默回退：静默回退会让「跑的是哪份代码」
# 变得不可知，比报错更糟。
REPOS_DIR="${REPOS_DIR:-${ROOT}}"
if [ ! -d "${REPOS_DIR}/zg-tsp-server" ] || [ ! -d "${REPOS_DIR}/zg-tsp-web" ]; then
  echo "✗ 代码目录无效：${REPOS_DIR}" >&2
  echo "  需要其中同时存在 zg-tsp-server/ 与 zg-tsp-web/。" >&2
  exit 1
fi
REPOS_DIR="$(cd "${REPOS_DIR}" && pwd -P)"

SERVER_PORT="${SERVER_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
API_TARGET="${API_TARGET:-http://127.0.0.1:${SERVER_PORT}}"
LOG_DIR="${LOG_DIR:-${ROOT}/.dev-logs}"
PID_FILE="${LOG_DIR}/dev.pids"

# start_bg 用它给子进程注入环境变量（空格分隔的 VAR=VAL 列表）。
BG_ENV=""

# --- 颜色 ---
# 用 printf 生成 ESC 字符（\033 是 POSIX printf 支持的八进制转义），
# 而不是 bash 专有的 $'\033[0;31m' 写法。
if [ -t 1 ]; then
  ESC=$(printf '\033')
  R="${ESC}[0;31m"; G="${ESC}[0;32m"; Y="${ESC}[0;33m"; B="${ESC}[0;36m"; N="${ESC}[0m"
else
  R=""; G=""; Y=""; B=""; N=""
fi

info()  { echo "${B}==>${N} $*"; }
ok()    { echo "  ${G}✓${N} $*"; }
warn()  { echo "  ${Y}!${N} $*"; }
err()   { echo "  ${R}✗${N} $*" >&2; }

# --- 工具函数 ---

port_busy() {
  lsof -ti:"$1" >/dev/null 2>&1
}

free_port() {
  local port="$1" name="$2"
  if port_busy "$port"; then
    err "端口 ${port} 已被占用（${name}）。"
    err "  查看占用：lsof -ti:${port}"
    err "  或换端口启动：SERVER_PORT=8001 WEB_PORT=5174 $0"
    return 1
  fi
  return 0
}

server_python() {
  if [ -n "${VENV_PY:-}" ] && [ -x "${VENV_PY}" ]; then
    echo "$VENV_PY"
  elif [ -x "${ROOT}/.venv/bin/python" ]; then
    echo "${ROOT}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    echo "python3"
  else
    return 1
  fi
}

start_bg() {
  # $1=名称 $2=工作目录 $3..=命令
  local name="$1" dir="$2"; shift 2
  mkdir -p "$LOG_DIR"

  # 用 exec 让子进程**替换** shell，$! 才是真正的服务进程 pid；
  # 否则 $! 指向的是会立刻退出的 subshell，记录下来就停不掉。
  #
  # BG_ENV 若非空，会以 `env <VAR=VAL>...` 的形式前置到命令前。
  # 不能写成 `FOO=bar exec cmd ...`——exec 的前置赋值会被
  # 当成可执行文件名，所以这里统一走 env 命令。
  if [ -n "${BG_ENV:-}" ]; then
    # shellcheck disable=SC2086
    ( cd "$dir" && exec env ${BG_ENV} "$@" ) > "${LOG_DIR}/${name}.log" 2>&1 &
  else
    ( cd "$dir" && exec "$@" ) > "${LOG_DIR}/${name}.log" 2>&1 &
  fi
  local pid=$!

  # PID 文件格式：<模块名> <pid>，启动时只替换本模块的记录，
  # 不影响其他模块（端口占用提前退出时也能保留旧记录）。
  local tmp="${PID_FILE}.tmp"
  if [ -f "$PID_FILE" ]; then
    grep -v "^${name} " "$PID_FILE" > "$tmp" 2>/dev/null || true
  else
    : > "$tmp"
  fi
  echo "${name} ${pid}" >> "$tmp"
  mv "$tmp" "$PID_FILE"

  ok "${name} 已启动 (pid ${pid})  日志：${LOG_DIR}/${name}.log"
}

wait_for_port() {
  # $1=端口 $2=超时秒数 $3=名称
  local port="$1" timeout="$2" name="$3" i=0
  while [ $i -lt $((timeout * 2)) ]; do
    if port_busy "$port"; then
      return 0
    fi
    sleep 0.5
    i=$((i + 1))
  done
  err "${name} 启动超时（${timeout}s），查看日志：${LOG_DIR}/${name}.log"
  tail -n 15 "${LOG_DIR}/${name}.log" 2>/dev/null | sed 's/^/      /'
  return 1
}

# --- 启动各模块 ---

start_server() {
  info "启动服务端 zg-tsp-server (:${SERVER_PORT})"
  local py; py="$(server_python)" || { err "找不到 Python 解释器"; return 1; }
  if ! ( cd "${REPOS_DIR}/zg-tsp-server" && "$py" -c "import fastapi, uvicorn" 2>/dev/null ); then
    warn "服务端依赖未安装，跳过。安装命令："
    echo "      cd ${REPOS_DIR}/zg-tsp-server && ${py} -m pip install -r requirements.txt"
    return 0
  fi
  if ! free_port "${SERVER_PORT}" "服务端"; then
    return 1
  fi
  BG_ENV=""
  start_bg server "${REPOS_DIR}/zg-tsp-server" \
    "$py" -m uvicorn app.main:app --host 127.0.0.1 --port "${SERVER_PORT}" --reload
  wait_for_port "${SERVER_PORT}" 20 "服务端" || return 1
}

start_web() {
  info "启动 Web 端 zg-tsp-web (:${WEB_PORT})"
  if ! command -v npm >/dev/null 2>&1; then
    err "找不到 npm"; return 1
  fi
  if [ ! -d "${REPOS_DIR}/zg-tsp-web/node_modules" ]; then
    warn "Web 端依赖未安装，正在安装（首次较慢）..."
    ( cd "${REPOS_DIR}/zg-tsp-web" && npm install ) > "${LOG_DIR}/web-install.log" 2>&1 \
      || { err "npm install 失败，见 ${LOG_DIR}/web-install.log"; return 1; }
  fi
  if ! free_port "${WEB_PORT}" "Web 端"; then
    return 1
  fi
  # 代理目标通过环境变量注入，不改动仓库内文件。
  # 用 BG_ENV（由 start_bg 转成 `env VAR=VAL` 前缀），
  # 避免依赖「变量前缀作用于函数调用」这一各 shell 语义略有差异的行为。
  BG_ENV="VITE_PROXY_TARGET=${API_TARGET}"
  start_bg web "${REPOS_DIR}/zg-tsp-web" npm run dev -- --port "${WEB_PORT}"
  BG_ENV=""
  wait_for_port "${WEB_PORT}" 25 "Web 端" || return 1
}

# --- 停止 / 状态 ---

stop_all() {
  info "停止所有进程"

  if [ -f "$PID_FILE" ]; then
    # 用 xargs 读 pid 列表：避免 `while read` 消耗脚本 stdin
    while read -r name pid; do
      [ -n "${pid:-}" ] || continue
      if kill -0 "$pid" 2>/dev/null; then
        # 杀掉整个进程组（npm run dev 会派生子进程）
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
        echo "  ${G}✓${N} 已停止 ${name} (pid ${pid})"
      fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  else
    warn "没有进程记录，仅按端口清理"
  fi

  # 兜底：等端口释放，超时则强杀
  for port in "${SERVER_PORT}" "${WEB_PORT}"; do
    pids="$(lsof -ti:"${port}" 2>/dev/null || true)"
    [ -n "$pids" ] || continue
    for pid in $pids; do
      kill "$pid" 2>/dev/null || true
    done
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      port_busy "$port" || break
      sleep 0.3
    done
    if port_busy "$port"; then
      for pid in $(lsof -ti:"${port}" 2>/dev/null); do
        kill -9 "$pid" 2>/dev/null || true
      done
      ok "端口 ${port} 强制释放"
    fi
  done
}

show_status() {
  echo
  info "模块运行状态"
  printf "  %-22s %-8s %s\n" "模块" "端口" "状态"
  for entry in "服务端:${SERVER_PORT}" "Web 端:${WEB_PORT}"; do
    local name="${entry%%:*}" port="${entry##*:}"
    if port_busy "$port"; then
      printf "  %-22s %-8s %s\n" "${name}" "${port}" "${G}运行中${N}"
    else
      printf "  %-22s %-8s %s\n" "${name}" "${port}" "未运行"
    fi
  done
  echo
  info "日志目录：${LOG_DIR}"
  ls -1 "${LOG_DIR}" 2>/dev/null | sed 's/^/      /'
}

tail_logs() {
  [ -d "$LOG_DIR" ] || { warn "还没有日志目录"; return 0; }
  # POSIX sh 没有数组，也没有 < <(...) 进程替换。
  # 改为把日志文件列表写进临时文件，再逐行读取传给 tail -f，
  # 这样文件名含空格也不会被拆成多个参数。
  local list_file
  list_file="$(mktemp "${TMPDIR:-/tmp}/zg-tsp-logs.XXXXXX")" || {
    warn "无法创建临时文件"; return 1;
  }
  # shellcheck disable=SC2064
  trap "rm -f '${list_file}'" EXIT INT TERM HUP

  ls -1 "${LOG_DIR}"/*.log > "$list_file" 2>/dev/null || true

  if [ ! -s "$list_file" ]; then
    warn "暂无日志"
    rm -f "$list_file"
    trap - EXIT INT TERM HUP
    return 0
  fi

  # 先把日志文件路径都读到位置参数，再交给 tail -f。
  # xargs 把换行转成参数分隔，但含空格的文件名仍会被拆开，
  # 所以这里用 IFS= read 逐行累积到 "$@"。
  local f
  set --
  while IFS= read -r f; do
    [ -n "$f" ] && set -- "$@" "$f"
  done < "$list_file"

  tail -f "$@"

  rm -f "$list_file"
  trap - EXIT INT TERM HUP
  return 0
}

# --- 主流程 ---

mkdir -p "$LOG_DIR"

# PID 文件只在**确实要启动进程**时才清空。
# stop / status / logs 是管理命令，截断会把已有进程记录抹掉；
# 而启动命令若因端口占用提前退出，也不该清 —— 否则会丢掉旧记录。
# 因此清空动作推迟到 start_bg 真正拉起进程之前（见 start_bg）。

CMD="${1:-start}"

case "${CMD}" in
  server)  start_server ;;
  web)     start_web ;;
  all)
    start_server && start_web
    ;;
  stop)    stop_all ;;
  status)  show_status ;;
  logs)    tail_logs ;;
  start)
    start_server && start_web
    ;;
  *)
    err "未知命令：$1"
    echo "用法：$0 {start|server|web|all|stop|status|logs}"
    exit 1
    ;;
esac

# status 命令在 case 内已打印过一次，这里不再重复
if [ "${CMD}" != "status" ]; then
  echo
  show_status
fi

if [ "${CMD}" != "stop" ] && [ "${CMD}" != "status" ] && [ "${CMD}" != "logs" ]; then
  echo
  info "提示：查看日志 ./scripts/dev.sh logs    停止全部 ./scripts/dev.sh stop"
  echo "  Web 端： http://localhost:${WEB_PORT}"
  # 健康检查是 POST-only 路由，直接用浏览器打开会返回 405
  echo "  服务端： curl -X POST ${API_TARGET%/}/homework_api/health"
  echo
fi
```

**与旧版的关键差异**（对照旧脚本确认已全部落实）：

| 旧内容 | 新内容 |
|---|---|
| `find_repos_dir()` 探测 4 个候选位置 | 单行 `REPOS_DIR="${REPOS_DIR:-${ROOT}}"` + 有效性校验 |
| `count_diff_files()` / 「与本快照的差异」 | 已删除 |
| `report_module_git()` / `report_source()` 整段 | 已删除 |
| 「代码来源与新鲜度」报告 | 已删除（改为启动时由 `info` 打印模块名） |
| `diff_exclude_args()`（约 30 行排除清单） | 随 diff 统计一并删除 |

- [ ] **Step 4: 保留可执行位**

```bash
cd /Users/zg/PycharmProjects/zg-homework
chmod +x scripts/dev.sh
ls -l scripts/dev.sh
```

Expected: `-rwxr-xr-x ... scripts/dev.sh`。

- [ ] **Step 5: 运行冒烟测试，确认通过**

```bash
cd /Users/zg/PycharmProjects/zg-homework
bash docs/test_dev_sh.sh
```

Expected: 全部小节 ✓，最后一行 `全部通过`，退出码 0。

若第 [4] 项失败（端口未监听），查看 `.dev-logs/server.log`：
```bash
tail -n 20 .dev-logs/server.log
```
常见原因：`.venv` 里没装 uvicorn —— 用 `.venv/bin/python -m pip install -r zg-tsp-server/requirements.txt` 补齐。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add scripts/dev.sh
git commit -m "refactor(dev): dev.sh 收敛为单仓库形态

移除多检出探测、快照差异统计与聚合仓库标注；REPOS_DIR 仅作显式覆盖，
无效时直接报错退出。保留启停语义与 POSIX sh 兼容性。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

`docs/test_dev_sh.sh` 属 gitignored 的本地资产，**不加入 commit**。

---

## Task 3: 简化 `scripts/init.sh` 的代码目录定位

**Files:**
- Modify: `scripts/init.sh`（改两处：头部注释 + 目录定位段）

**Interfaces:**
- Consumes: 无
- Produces: `scripts/init.sh` 的 `REPOS_DIR` 语义变为「默认 `$ROOT`，显式覆盖后须含 `zg-tsp-docs/sql/init.sql` 与 `zg-tsp-server/`，否则报错退出」。其余行为（`DATABASE_URL` 解析、admin 哈希生成、占位符替换、数量校验）**完全不变**。

- [ ] **Step 1: 改写头部注释中的探测顺序说明**

在 `scripts/init.sh` 中找到：

```
# 环境变量：
#   REPOS_DIR            仓库所在目录（默认自动探测，顺序与 dev.sh 不同）
```

替换为：

```
# 环境变量：
#   REPOS_DIR            代码目录（默认脚本所在仓库；显式指定时须含
#                        zg-tsp-docs/sql/init.sql 与 zg-tsp-server/）
```

- [ ] **Step 2: 替换目录定位段**

在 `scripts/init.sh` 中找到整段：

```sh
# --- 定位仓库目录 ---
# 初始化脚本探测顺序：环境变量 → ../zg-homework-repos → 本快照 → ~/zg-homework-repos
# 与 dev.sh 默认顺序不同；使用前须确认 SQL 和数据库来源。
REPOS_DIR_ENV="${REPOS_DIR:-}"
REPOS_DIR=""
find_repos_dir() {
  local candidates d
  candidates=$(printf '%s\n' \
    "${REPOS_DIR_ENV}" \
    "${ROOT}/../zg-tsp-repos" \
    "${ROOT}" \
    "${HOME}/zg-tsp-repos"
  )
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    if [ -f "$d/zg-tsp-docs/sql/init.sql" ] && [ -d "$d/zg-tsp-server" ]; then
      REPOS_DIR="$(cd "$d" && pwd -P)"
      return 0
    fi
  done <<EOF
${candidates}
EOF
  return 1
}

find_repos_dir || die "找不到包含 zg-tsp-docs/sql/init.sql 的仓库目录。
请在仓库根目录执行，或用 REPOS_DIR=<路径> 指定。"
```

整段替换为：

```sh
# --- 定位代码目录 ---
# 默认就是本仓库（单一仓库，代码唯一来源）。
# REPOS_DIR 只作显式覆盖；覆盖值无效时直接报错，不静默回退。
REPOS_DIR="${REPOS_DIR:-${ROOT}}"
if [ ! -f "${REPOS_DIR}/zg-tsp-docs/sql/init.sql" ] || [ ! -d "${REPOS_DIR}/zg-tsp-server" ]; then
  die "代码目录无效：${REPOS_DIR}
需要其中同时存在 zg-tsp-docs/sql/init.sql 与 zg-tsp-server/。"
fi
REPOS_DIR="$(cd "${REPOS_DIR}" && pwd -P)"
```

- [ ] **Step 3: 语法检查**

```bash
cd /Users/zg/PycharmProjects/zg-homework
for s in sh bash zsh; do printf "%-5s -n init.sh: " "$s"; $s -n scripts/init.sh && echo OK; done
```

Expected: 三行 `OK`。

- [ ] **Step 4: 验证无效 REPOS_DIR 会报错**

```bash
cd /Users/zg/PycharmProjects/zg-homework
REPOS_DIR=/tmp/nope ./scripts/init.sh --help >/dev/null 2>&1; echo "退出码 $?"
```

Expected: 退出码 0 —— `--help` 在参数解析阶段就退出（`exit 0`），**不会走到目录定位**，所以这条不能验证定位逻辑。

改用真正会走到定位逻辑的调用（会因找不到 mysql 客户端或库而失败，但错误信息必须是「代码目录无效」）：

```bash
cd /Users/zg/PycharmProjects/zg-homework
REPOS_DIR=/tmp/nope ./scripts/init.sh 2>&1 | head -3
```

Expected: 输出首行为 `✗ 代码目录无效：/tmp/nope`（`die` 走 `err()`，带 `✗` 前缀与颜色码）。

若输出了别的错误（例如「找不到 mysql 客户端」），说明目录定位段没有被替换成功。

- [ ] **Step 5: 验证默认路径能正确解析出 SQL 文件**

```bash
cd /Users/zg/PycharmProjects/zg-homework
sh -x scripts/init.sh 2>&1 | grep -E "INIT_SQL=|SERVER_DIR=" | head -4
```

Expected: 输出中 `INIT_SQL=` 指向 `<仓库根>/zg-tsp-docs/sql/init.sql`，`SERVER_DIR=` 指向 `<仓库根>/zg-tsp-server`。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add scripts/init.sh
git commit -m "refactor(init): init.sh 代码目录定位收敛为单仓库

移除 ../zg-tsp-repos 与 ~/zg-tsp-repos 的自动探测，REPOS_DIR 仅作显式覆盖，
无效时直接报错。数据库初始化逻辑不变。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: `independence_check.py` 改为「模块边界检查」

**Files:**
- Modify: `zg-tsp-docs/scripts/independence_check.py`（改文档字符串、标题输出、1 处检查项名称）

**Interfaces:**
- Consumes: 无
- Produces: 脚本仍从 `zg-tsp-docs/scripts/independence_check.py` 向上两级定位仓库根（`ROOT`），检查项数量仍为 8，判定逻辑完全不变。唯一变化：**语义与文案**从「独立仓库」改为「单仓内的模块边界」。

- [ ] **Step 1: 改写模块文档字符串**

找到文件开头的 docstring：

```python
"""模块独立性检查（PRD 第 12 节「模块独立性」）。

静态分析各模块的源码与配置，不依赖运行时。
用法：
    python zg-homework-docs/scripts/independence_check.py

需在**聚合仓库**（各模块同级检出）下运行；若缺少任一模块则跳过对应检查。
"""
```

整段替换为：

```python
"""模块边界检查（PRD 第 12 节「模块边界」）。

静态分析各模块的源码与配置，不依赖运行时。
三个模块位于**同一仓库**的独立目录中；本检查确保它们之间不越界。

用法：
    python zg-homework-docs/scripts/independence_check.py

需在**仓库根**下运行（脚本按自身位置向上两级定位根目录）。
"""
```

- [ ] **Step 2: 改标题输出**

找到：

```python
    print("\n=== 模块独立性检查 ===")
```

替换为：

```python
    print("\n=== 模块边界检查 ===")
```

- [ ] **Step 3: 改第 1 项检查名称**

找到：

```python
    check(not missing, "1. 各模块有独立依赖清单",
```

替换为：

```python
    check(not missing, "1. 各模块有独立依赖清单（依赖自封闭）",
```

其余 7 项的名称与逻辑**保持不变** —— 检查项实质全部保留，只是语义归属从「独立仓库之间」变为「单仓内模块之间」。

- [ ] **Step 4: 运行检查，确认 8/8 通过**

```bash
cd /Users/zg/PycharmProjects/zg-homework
.venv/bin/python zg-homework-docs/scripts/independence_check.py
```

Expected:
```
=== 模块边界检查 ===
  ✅ 1. 各模块有独立依赖清单（依赖自封闭）  — requirements / package.json
  ...
=== 独立性检查：8/8 通过 ===
```

（最后一行汇总文案「=== 独立性检查：8/8 通过 ===」在本次**不改**，属汇总行；若要一并改为「模块边界检查：8/8 通过」也可接受 —— 二选一，保持全文一致即可。）

退出码应为 0。

- [ ] **Step 5: 确认脚本内无残留的「独立仓库」措辞**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "独立仓库\|聚合" zg-homework-docs/scripts/independence_check.py
```

Expected: 无输出。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-docs/scripts/independence_check.py
git commit -m "refactor(docs): independence_check 改为模块边界检查语义

检查项实质与判定逻辑全部保留，仅改标题、文案与文档字符串；
仓库根定位改为按脚本自身位置向上两级。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 新增根级 `Makefile`

**Files:**
- Create: `Makefile`

**Interfaces:**
- Consumes: Task 2 产出的 `scripts/dev.sh` 子命令；Task 3 产出的 `scripts/init.sh`；Task 4 产出的 `independence_check.py`。
- Produces: 根级统一入口，目标：`help`（默认）/ `dev` / `server` / `web` / `stop` / `status` / `logs` / `db-init` / `test` / `build` / `check` / `clean-logs`。`db-init` 支持 `ARGS=--drop` 透传。

- [ ] **Step 1: 创建 `Makefile`**

```make
# zg-tsp 统一入口
#
# 单一仓库，三个模块目录：zg-tsp-server / zg-tsp-web / zg-tsp-docs。
#
# 用法：make help

SHELL := /bin/sh
ROOT  := $(shell pwd)

SERVER_DIR := $(ROOT)/zg-tsp-server
WEB_DIR    := $(ROOT)/zg-tsp-web
DOCS_DIR   := $(ROOT)/zg-tsp-docs

# Python 解释器：优先仓库根的 .venv，其次 python3（与 dev.sh 的 server_python 策略一致）
PY := $(shell if [ -x "$(ROOT)/.venv/bin/python" ]; then echo "$(ROOT)/.venv/bin/python"; else echo python3; fi)

.DEFAULT_GOAL := help

.PHONY: help dev server web stop status logs db-init test build check clean-logs

help: ## 显示本帮助
	@echo "zg-tsp —— 单一仓库（服务端 / Web 端 / 文档）"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "注意：test 与 check 会写入真实数据库，请指向隔离库。"

dev: ## 启动服务端 + Web 端
	@$(ROOT)/scripts/dev.sh

server: ## 只启动服务端
	@$(ROOT)/scripts/dev.sh server

web: ## 只启动 Web 端
	@$(ROOT)/scripts/dev.sh web

stop: ## 停止本脚本启动的进程
	@$(ROOT)/scripts/dev.sh stop

status: ## 查看各模块运行状态
	@$(ROOT)/scripts/dev.sh status

logs: ## 跟随查看日志
	@$(ROOT)/scripts/dev.sh logs

db-init: ## 初始化数据库（幂等；加 ARGS=--drop 可删库重建）
	@$(ROOT)/scripts/init.sh $(ARGS)

test: ## 跑服务端 pytest（需可连的 MySQL）
	@cd $(SERVER_DIR) && $(PY) -m pytest

build: ## 构建 Web 端（tsc 类型检查 + vite build）
	@cd $(WEB_DIR) && npm run build

check: ## 跑模块边界检查 + 业务验收（业务验收需服务端已启动）
	@cd $(ROOT) && $(PY) $(DOCS_DIR)/scripts/independence_check.py
	@cd $(ROOT) && $(PY) $(DOCS_DIR)/scripts/acceptance_check.py

clean-logs: ## 清空 .dev-logs
	@rm -rf $(ROOT)/.dev-logs
```

**两处易错点**（已在上面规避，勿改）：

- `awk` 的 `FS` 用**贪婪**的 `":.*## "` —— macOS 的 BSD awk 不支持非贪婪 `.*?`。
- grep 模式里的 `$$` 是 make 的转义，转到 shell 后是 `$`（行尾锚点）。

- [ ] **Step 2: 验证 `make help`**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make help
```

Expected: 输出标题行 + 目标列表（`dev`、`server`、`web`、`stop`、`status`、`logs`、`db-init`、`test`、`build`、`check`、`clean-logs`）+ 末尾的数据库提示行。

若目标列表为空 → `grep` 模式与 `awk` 字段分隔不匹配（检查目标行是否真的带 `## `）。

- [ ] **Step 3: 验证 `make status` 能透传到 dev.sh**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make status
```

Expected: 输出含「模块运行状态」与「服务端 / Web 端」两行。

- [ ] **Step 4: 验证 `make check` 的前半段（模块边界检查）能跑通**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make -n check
```

Expected: 打印两行将要执行的命令（`make -n` 只打印不执行），确认路径拼接正确：

```
cd /Users/zg/PycharmProjects/zg-tsp && /Users/zg/PycharmProjects/zg-tsp/.venv/bin/python /Users/zg/PycharmProjects/zg-tsp/zg-tsp-docs/scripts/independence_check.py
cd /Users/zg/PycharmProjects/zg-tsp && /Users/zg/PycharmProjects/zg-tsp/.venv/bin/python /Users/zg/PycharmProjects/zg-tsp/zg-tsp-docs/scripts/acceptance_check.py
```

- [ ] **Step 5: 验证 `make build`**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make build 2>&1 | tail -15
```

Expected: `tsc -b && vite build` 成功，输出 `✓ built in ...`。退出码 0。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add Makefile
git commit -m "feat(make): 新增根级 Makefile 统一入口

单仓库三模块的常用命令收拢到根级：dev / server / web / stop / status /
logs / db-init / test / build / check / clean-logs。不引入新依赖。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 删除 `scripts/split_repos.sh`

**Files:**
- Delete: `scripts/split_repos.sh`

**Interfaces:**
- Consumes: 无
- Produces: 仓库内不再存在拆分脚本；`split/*` 分支与 `../zg-tsp-repos/` 的删除在 Task 12。

- [ ] **Step 1: 确认没有其它文件引用它**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -rn "split_repos" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=superpowers --exclude-dir=docs
```

Expected: 输出会列出 `CLAUDE.md`、`README.md`、`zg-tsp-docs/README.md`、`zg-tsp-docs/sys_doc/PRD.md`、`zg-tsp-docs/sys_doc/小程序.md` 等**待改的文档**（Tasks 8-11 处理）以及 `scripts/split_repos.sh` 自身。

若出现**其它**未预期的文件（如某个 `.py` 或 `.sh` 依赖它），停下并把该文件加入本任务的删除范围评估。

- [ ] **Step 2: 删除文件**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git rm scripts/split_repos.sh
```

- [ ] **Step 3: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git commit -m "chore: 移除 split_repos.sh 拆分脚本

单一仓库形态下不再需要 subtree 拆分流程。四个 split/* 分支与
../zg-tsp-repos/ 的清理见后续提交。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 重写根 `README.md`

**Files:**
- Modify: `README.md`（整文件重写）

**Interfaces:**
- Consumes: Task 5 的 Makefile 目标名。
- Produces: 根 README 描述单仓库三模块，提供 Makefile 入口。

- [ ] **Step 1: 整文件替换 `README.md`**

```markdown
# zg-tsp

学习兴趣培养积分系统 —— **单一仓库**，服务端 / Web 端 / 文档三模块同处一个检出。

| 模块目录 | 内容 | 技术栈 |
|------|------|--------|
| `zg-tsp-server/` | 服务端 | Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 |
| `zg-tsp-web/` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 / Zustand 5 |
| `zg-tsp-docs/` | **文档与契约**（PRD、配置、验收脚本） | Markdown / Python |

微信小程序端是**仓外独立仓库**，位于 `~/WeChatProjects/HomeworkPoints`，
规划与验收见 [`zg-tsp-docs/sys_doc/小程序.md`](zg-tsp-docs/sys_doc/小程序.md)。

三个模块**目录独立、边界清晰**：各自有依赖清单（`requirements.txt` / `package.json`）、
各自可单独安装依赖、单独启动、单独打包，模块间零代码引用，只通过 HTTP 接口通信
（原则见 [PRD §2.2.1](zg-tsp-docs/sys_doc/PRD.md)）。

## 快速开始

```bash
# 安装服务端依赖
cd zg-tsp-server && pip install -r requirements.txt && cd ..

# 安装 Web 端依赖
cd zg-tsp-web && npm install && cd ..

# 一键启动（服务端 + Web 端）
make dev
```

| 入口 | 命令 |
|------|------|
| 启动服务端 + Web 端 | `make dev` |
| 只启动服务端 / Web 端 | `make server` / `make web` |
| 停止 / 状态 / 日志 | `make stop` / `make status` / `make logs` |
| 初始化数据库 | `make db-init`（`make db-init ARGS=--drop` 删库重建） |
| 跑服务端测试 | `make test` |
| 构建 Web 端 | `make build` |
| 模块边界检查 + 业务验收 | `make check` |

Web 端：<http://localhost:5173>
服务端健康检查（**POST-only**，浏览器直接打开会 405）：

```bash
curl -X POST http://127.0.0.1:8000/homework_api/health
# {"code":0,"message":"ok","data":{"status":"ok","env":"dev"}}
```

## 手工启动（不用 Makefile）

```bash
# 终端 1：服务端
cd zg-homework-server && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：Web 端（Vite 代理 /homework_api → 127.0.0.1:8000，保留前缀）
cd zg-homework-web && npm run dev

# 终端 3：验收脚本
python zg-homework-docs/scripts/independence_check.py
python zg-homework-docs/scripts/acceptance_check.py
```

## 数据库初始化

部署到空机器时，一条命令完成「建库 → 建表 → 写积分规则及批改档位 → 建 admin」：

```bash
./scripts/init.sh              # 幂等，可重复执行
./scripts/init.sh --drop       # 先删库重建（危险，需二次确认）
```

它导入的是 `zg-tsp-docs/sql/init.sql` —— 该文件由 `python -m app.seed.export_ddl`
从 ORM 生成，含全部表的中文 COMMENT。admin 初始密码取 `ADMIN_INIT_PASSWORD`
环境变量，未设则随机生成。仅在本次密码生效时显示随机密码或提示使用了环境变量，首登强制改密。已有正常密码不会被覆盖，`ADMIN_INIT_PASSWORD` 不能用于强制重置密码；已有 admin 的密码哈希恰为 `__ADMIN_BCRYPT_HASH__` 时会被修复。直接导入未经替换的 SQL 会创建表和规则，但不会创建 admin；应使用初始化脚本，或先将占位符替换为有效 bcrypt 哈希再导入。

需要联调数据（测试账号、班级、成语题库）时，另跑 `python -m app.seed.initial_data`。

## 功能范围

**四角色**（admin / teacher / student / parent）× **两平台**（小程序 + Web）全覆盖。
小程序端老师 / admin 端按 PRD §9.6 排在二期。

| 模块 | Phase | 状态 |
|------|-------|------|
| 服务端 | P1 认证（JWT + 老师邀请码一码一用） | ✅ |
| 服务端 | P1b MySQL 15 张表 + 全字段中文注释 | ✅ |
| 服务端 | P1.5 admin 基础（邀请码 / 用户 / 统计） | ✅ |
| 服务端 | P1.6 积分规则管理 + 规则缓存 + 积分发放 | ✅ |
| 服务端 | P2 班级与作业（打点 / 迟交 / 用时） | ✅ |
| 服务端 | P3 签到与排行榜 | ✅ |
| 服务端 | P4 家长绑定与扣分 | ✅ |
| 服务端 | P5 课后阅读（心跳防挂机） | ✅ |
| 服务端 | P6 数独 + 成语接龙 + 题库管理 | ✅ |
| Web | P7 四角色页面 | ✅ |
| 小程序 | P8 四角色页面（原生小程序，仓外独立仓库） | 🔄 一期学生 + 家长 |
| 全局 | P9 联调验收 | ✅ |

## 验证状态

| 检查项 | 结果 |
|--------|------|
| 服务端 pytest | 294 passed |
| PRD 业务验收（第 12 节） | 34 通过 / 0 失败（11 项主动跳过以免污染共享数据） |
| 模块边界检查 | 8/8 |
| Web `tsc` + `vite build` | ✅ |

## 文档

完整需求与契约见 [`zg-tsp-docs/sys_doc/PRD.md`](zg-tsp-docs/sys_doc/PRD.md)（v2.3）。
配置项见 [`zg-tsp-docs/sys_doc/config.md`](zg-tsp-docs/sys_doc/config.md)。
小程序端规划见 [`zg-tsp-docs/sys_doc/小程序.md`](zg-tsp-docs/sys_doc/小程序.md)。
```

- [ ] **Step 2: 验证无残留措辞**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
grep -n "独立仓库\|聚合检出\|聚合仓库\|拆分方式\|快照" README.md
```

Expected: 只允许出现「仓外独立仓库」（指小程序端）这一类**事实陈述**；不得出现「本仓库已拆分为 3 个独立仓库」「聚合检出」「拆分方式」等框架性表述。

- [ ] **Step 3: 验证 Makefile 目标在 README 中都有对应**

```bash
cd /Users/zg/PycharmProjects/zg-homework
for t in dev server web stop status logs db-init test build check; do
  grep -q "make $t" README.md && echo "  ✓ $t" || echo "  ✗ $t 缺失"
done
```

Expected: 11 行全部 `✓`。

- [ ] **Step 4: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add README.md
git commit -m "docs(readme): 根 README 改为单仓库口径

删除「已拆分为 3 个独立仓库」「聚合检出」「拆分方式」三节，
改写为单仓库三模块说明 + Makefile 入口。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: 重写 `zg-tsp-docs/README.md`

**Files:**
- Modify: `zg-tsp-docs/README.md`（整文件重写）

**Interfaces:**
- Consumes: 无
- Produces: 文档模块的 README，描述本模块在单仓中的职责。

- [ ] **Step 1: 整文件替换 `zg-tsp-docs/README.md`**

```markdown
# zg-tsp-docs

学习兴趣培养积分系统 —— **文档与契约模块**。

本模块是跨模块的**唯一权威契约来源**。三个模块同处一个仓库，
接口契约以本模块的 [PRD](sys_doc/PRD.md) 为准。

## 内容

| 路径 | 说明 |
|------|------|
| `sys_doc/PRD.md` | 完整产品需求文档 v2.3 —— 数据模型、接口清单、权限矩阵、验收标准 |
| `sys_doc/config.md` | 各环境配置项（数据库等） |
| `sys_doc/小程序.md` | 微信小程序端规划与验收（仓外独立仓库） |
| `sys_doc/迭代.md` | 迭代记录 |
| `sql/init.sql` | 部署用建表 SQL（由 `python -m app.seed.export_ddl` 从 ORM 生成） |
| `scripts/acceptance_check.py` | 业务验收脚本：对照 PRD 第 12 节逐条调真实接口验证 |
| `scripts/independence_check.py` | 模块边界静态检查：依赖自封闭、零跨模块引用、无硬编码地址 |
| `superpowers/specs/` | 设计文档 |
| `superpowers/plans/` | 实施计划 |

## 仓库结构

```
zg-tsp/
├── zg-tsp-docs/       ← 本模块
├── zg-tsp-server/
└── zg-tsp-web/
```

三个模块位于**同一仓库**的独立目录中，各自可**单独安装依赖、单独启动、单独打包**
（PRD §2.2.1），模块间只通过 HTTP 接口通信。

微信小程序端为**仓外独立仓库**（`~/WeChatProjects/HomeworkPoints`，原生小程序），
规划与验收见 [小程序.md](sys_doc/小程序.md)。

**四角色 × 两平台全覆盖**：学生 / 家长 / 老师 / admin 在小程序端与 Web 端均提供，
差异仅在交互形态（PRD 第 9 节）。小程序端老师 / admin 端按 PRD §9.6 排在二期。

## 验收脚本用法

需在仓库根下运行（脚本按自身位置向上两级定位根目录）：

```bash
# 1. 启动服务端
make server

# 2. 业务验收（PRD 第 12 节）
python zg-tsp-docs/scripts/acceptance_check.py

# 3. 模块边界检查
python zg-tsp-docs/scripts/independence_check.py
```

也可以用根级入口一次跑完：

```bash
make check
```

> `acceptance_check.py` 会自动确保 admin 可登录（必要时重置本地库密码）。
> 两个脚本都只读或写测试数据，**不删表**。

## 接口契约

全 POST + Body，参数不携带于 URL。统一响应：

```json
{ "code": 0, "message": "ok", "data": {} }
```

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

完整接口清单见 [PRD 第 7 节](sys_doc/PRD.md)。

## 变更约定

PRD 是跨模块契约，**修改 PRD 需同步各模块**：

- 新增/修改接口 → 服务端实现后，各客户端同步
- 修改字段语义（如 `daily_limit` 含义）→ 各模块都要改
- 数据模型变更 → 服务端迁移 + 客户端类型定义同步

各模块的客户端类型定义（`types.ts` / 小程序端 `utils/` 下的常量）以 PRD 为准，
但**它们是手工副本**，改 PRD 后需手动同步。
```

- [ ] **Step 2: 验证无残留措辞**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
grep -n "独立仓库\|聚合\|三个模块仓库\|各自的仓库" zg-tsp-docs/README.md
```

Expected: 只允许「仓外独立仓库」（指小程序端）与「只读或写测试数据」以外的**事实陈述**。

- [ ] **Step 3: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-docs/README.md
git commit -m "docs(docs): zg-tsp-docs README 改为单仓库口径

删除「三个模块仓库」「聚合检出」表述，改为单仓三模块目录 + 仓外小程序端。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: 更新 `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`（改 6 处）

**Interfaces:**
- Consumes: Task 2/3/5 的新形态（dev.sh 无 REPOS_DIR 探测、有 Makefile）。
- Produces: `CLAUDE.md` 与实际仓库形态一致。

- [ ] **Step 1: 改「仓库形态」章节（第 5-15 行附近）**

找到：

```markdown
## 仓库形态

本项目分为三个独立仓库，不是一个可整体构建的单体。**当前聚合检出只有 server、web、docs 三个目录**。微信小程序端是第四个独立仓库，位于 `~/WeChatProjects/HomeworkPoints`，**不在本检出中**。下表描述完整工作区，而非保证所有目录都在当前检出：

| 目录 | 内容 | 技术栈 |
|------|------|--------|
| `zg-tsp-server/` | 服务端 | Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 |
| `zg-tsp-web/` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 / Zustand 5 |
| `zg-tsp-docs/` | **契约与验收**（PRD、config、验收脚本） | Markdown / Python |
```

整段替换为：

```markdown
## 仓库形态

本项目是**单一仓库**（一个 git 仓库、一个检出），下含三个模块目录。微信小程序端是**仓外独立仓库**，位于 `~/WeChatProjects/HomeworkPoints`，**不在本检出中**。

| 目录 | 内容 | 技术栈 |
|------|------|--------|
| `zg-tsp-server/` | 服务端 | Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 |
| `zg-tsp-web/` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 / Zustand 5 |
| `zg-tsp-docs/` | **契约与验收**（PRD、config、验收脚本） | Markdown / Python |

三个模块**目录独立、边界保留**：各自有依赖清单、源码零跨模块引用、各自可单独启动与打包。仓库根的 `Makefile` 是统一入口。
```

- [ ] **Step 2: 改「三个必须知道的结构性事实」第 2 条**

找到：

```markdown
2. **`scripts/dev.sh` 默认优先启动本目录的代码**。有效的 `REPOS_DIR` 优先；否则探测 `$ROOT` → `../zg-tsp-repos` → `~/zg-tsp-repos`。若显式指定或回退到独立仓库，其代码可能与本检出不同步；改完代码后确认运行的是哪一份。
```

替换为：

```markdown
2. **`scripts/dev.sh` 启动本仓库的代码**。`REPOS_DIR` 可显式覆盖（如指向 git worktree），无效时直接报错退出——**不静默回退**。本仓库是唯一代码来源，没有别的检出需要同步。
```

- [ ] **Step 3: 改第 1 条（小程序端）**

找到：

```markdown
1. **微信小程序端是第四个独立仓库**，位于 `~/WeChatProjects/HomeworkPoints`，**不在当前聚合检出内**。它是原生小程序（WXML/WXSS/JS），规划与验收见 `zg-tsp-docs/sys_doc/小程序.md`。服务端与 Web 端无需为它做任何改动。
```

替换为：

```markdown
1. **微信小程序端是仓外独立仓库**，位于 `~/WeChatProjects/HomeworkPoints`，**不在本检出内**。它是原生小程序（WXML/WXSS/JS），规划与验收见 `zg-tsp-docs/sys_doc/小程序.md`。服务端与 Web 端无需为它做任何改动。
```

- [ ] **Step 4: 在「常用命令」前插入 Makefile 入口说明**

找到：

```markdown
## 常用命令

### 服务端
```

替换为：

```markdown
## 常用命令

### 根级入口（Makefile）

```bash
make help      # 列出全部目标
make dev       # 启动服务端 + Web 端
make server    # 只启动服务端
make web       # 只启动 Web 端
make stop      # 停止
make status    # 状态
make logs      # 日志
make db-init   # 初始化数据库（make db-init ARGS=--drop 删库重建）
make test      # 服务端 pytest（需可连的 MySQL）
make build     # Web tsc + vite build
make check     # 模块边界检查 + 业务验收（验收需服务端已启动）
```

### 服务端
```

- [ ] **Step 5: 删「本机构建环境」整节**

找到从 `## 本机构建环境` 开始、到 `## Git 约定` 之前的整段，**整节删除**。

要删除的**原文块**如下（从 `## 本机构建环境` 到 `## Git 约定` 之前）：

```markdown
## 本机构建环境

`../zg-tsp-repos/` 是本机三个独立仓库的检出。

**改动时务必确认使用的是哪份代码**：`scripts/dev.sh` 优先使用有效的 `REPOS_DIR`；
否则 `dev.sh` 优先 `$ROOT`，再探测 `../zg-tsp-repos` → `~/zg-tsp-repos`。
`init.sh` 的默认探测顺序**与 `dev.sh` 不同**（它先探 `../zg-tsp-repos`，本快照排其后），
初始化前确认来源。

无效或不完整的覆盖值可能回退自动探测；检查脚本输出。

`scripts/dev.sh` 现在会在启动前打印「代码来源与新鲜度报告」（REPOS_DIR 命中哪份代码、各模块 git 状态、与本快照的差异条目数），用它确认跑的是哪一份。
```

整段删除（含 `## 本机构建环境` 标题行）。删除后，`## Git 约定` 直接跟在「历史修复记录」之前。
**确认 `## Git 约定` 一节仍然存在**（它需要改写，见 Step 6）。

- [ ] **Step 6: 改「Git 约定」中的子树拆分段**

找到：

```markdown
- 主分支 `main`。三个独立仓库通过 `git subtree split --prefix=<模块>` 拆出，历史保留在 `split/<模块>` 分支（本地已有 `split/zg-tsp-server`、`split/zg-tsp-web`、`split/zg-tsp-docs`；`split/zg-tsp-android`、`split/zg-tsp-ios` 是移动端下线前的历史留存，可用于恢复）。
```

替换为：

```markdown
- 主分支 `main`，**单一仓库**。三个模块是同一仓库下的独立目录，模块边界保留（各自依赖清单、零跨模块引用、各自独立打包）。
- 合并前的历史曾用 `git subtree split` 拆成独立仓库，相关分支与检出已清理。移动端（Flutter）的源码仍保留在 `main` 的历史提交 `7bf7dd0` 之前，可随时恢复。
```

- [ ] **Step 7: 更新 CLAUDE.md 里的 PRD 版本引用**

找到「仓库形态」章节下方的这句话：

```markdown
**需求与 API 契约的权威来源是 `zg-tsp-docs/sys_doc/PRD.md`**（v2.2）。
```

把 `（v2.2）` 改为 `（v2.3）`。

同时检查全文是否还有指向当前 PRD 版本的引用：

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "PRD.md.*v2\.\|PRD（v2\." CLAUDE.md
```

Expected: 所有指向**当前**版本的引用都是 v2.3。「历史修复记录」里提到「PRD 2.1」「PRD 2.2.1」的是历史条目，**保留不动**（2.2.1 是章节号，不是版本号）。

- [ ] **Step 8: 更新「已知缺陷」第 6 条（若提到聚合/独立仓）**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "聚合\|独立仓库\|zg-tsp-repos\|split" CLAUDE.md
```

Expected: 只剩 Step 5/6 改写后允许的「仓外独立仓库」「移动端历史」类表述。若第 6 条（nginx 反代无 compose 支撑）仍提到「裸机部署走「云服务器部署」一节的 `scripts/package.sh`」，保留即可 —— 与本次改动无关。

- [ ] **Step 9: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add CLAUDE.md
git commit -m "docs(claude): CLAUDE.md 改为单仓库形态

仓库形态、结构性事实、根级 Makefile 入口、本机构建环境与 Git 约定
四处同步，删除已废弃的 ../zg-tsp-repos 探测说明。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: 更新 `PRD.md`（决策 6 改写）

**Files:**
- Modify: `zg-tsp-docs/sys_doc/PRD.md`（改 9 处：标题、§0 变更记录、§2.2、§2.2.1、§2.2.2、§9.6、§11、§12、§13、§13.1）

**Interfaces:**
- Consumes: 无
- Produces: PRD v2.3，决策 6 改为「单仓三模块目录，模块边界保留」。

- [ ] **Step 1: 改标题与 §0 变更记录**

标题行改为：

```markdown
# 学习兴趣培养积分系统 — 完整 PRD（v2.3）
```

在 `### v2.2（移除 Flutter 移动端）` **之前**插入：

```markdown
### v2.3（单一仓库化）

| # | 变更 | 说明 |
|---|------|------|
| 1 | 仓库形态改为单仓 | 三个模块从「拆分为独立仓库」改为**同一仓库的独立目录**（`zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/`）。决策 6 修订，§2.2 / §2.2.1 / §2.2.2 / §9.6 / §11 / §12 / §13 / §13.1 同步。 |
| 2 | 模块边界保留 | 依赖自封闭、零跨模块源码引用、配置外置、单独启动、单独打包、版本契约六条原则全部保留，仅语义从「独立仓库之间」改为「单仓内模块之间」。 |
| 3 | 小程序端定位不变 | 仍是**仓外独立仓库**（`~/WeChatProjects/HomeworkPoints`），事实未变，措辞由「第四个独立仓库」统一为「仓外独立仓库」。 |
```

- [ ] **Step 2: 改 §2.2 项目结构**

第 94-95 行：

```markdown
按端/形态拆分为三个**相互独立**的模块。每个模块可单独启动、单独打包、单独发版，
任一模块的构建/发布**不影响**其他模块——彼此唯一的耦合是服务端接口契约。
```

改为：

```markdown
按端/形态拆分为三个**相互独立**的模块，置于**同一仓库**的独立目录中。
每个模块可单独安装依赖、单独启动、单独构建与发布，
任一模块的构建/发布**不影响**其他模块——彼此唯一的耦合是服务端接口契约。
```

第 101-102 行：

```markdown
> **小程序端**：微信原生小程序（WXML/WXSS/JS），**独立仓库，位于本聚合检出之外**，
> 不参与本目录的拆分与联调。其规划见 [小程序.md](小程序.md)。
```

改为：

```markdown
> **小程序端**：微信原生小程序（WXML/WXSS/JS），**仓外独立仓库，不在本检出内**，
> 不参与本目录的联调。其规划见 [小程序.md](小程序.md)。
```

第 105 行目录树注释：

```
workspace/                            # 三个独立仓库同级检出（联调用）
```

改为：

```
zg-tsp/                               # 单一仓库，三个模块目录
```

第 146-151 行的两段引用（`**仓库形态（决策 6）**` 与 `**决策 6**`）**整段替换**为一段：

```markdown
> **决策 6（2026-11-12 修订）**：三个模块置于**同一仓库**的独立目录中
> （`zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/`），各模块保留独立依赖清单与
> 独立打包能力，模块间零代码引用（见 2.2.1）。接口契约以第 7 节为唯一权威来源。
> 微信小程序端为**仓外独立仓库**，不在本检出内。
```

- [ ] **Step 3: 改 §2.2.1 标题**

```markdown
#### 2.2.1 模块独立性原则
```

改为：

```markdown
#### 2.2.1 模块边界原则
```

表格六行**内容全部保留不动**。

- [ ] **Step 4: 改 §2.2.2 小程序端段落**

第 192 行：

```markdown
小程序端是**独立仓库**，位于本聚合检出之外，不参与本目录的拆分与联调。
```

改为：

```markdown
小程序端是**仓外独立仓库**，不在本检出内，不参与本目录的联调。
```

- [ ] **Step 5: 改 §9.6**

第 1056 行：

```markdown
> 小程序端为**独立仓库**（决策 6），位于本聚合检出之外，功能范围与排期见
```

改为：

```markdown
> 小程序端为**仓外独立仓库**（决策 6），不在本检出内，功能范围与排期见
```

- [ ] **Step 6: 改 §11 开发计划 P8 行**

第 1108 行：

```markdown
| P8    | 小程序端        | **四角色**页面：学生 / 家长 / 老师 / admin（独立仓库，一期学生 + 家长）                  |
```

改为：

```markdown
| P8    | 小程序端        | **四角色**页面：学生 / 家长 / 老师 / admin（仓外独立仓库，一期学生 + 家长）                  |
```

- [ ] **Step 7: 改 §12 验收标准「模块独立性」清单组**

把该组的标题行：

```markdown
**模块独立性**
```

改为：

```markdown
**模块边界**
```

组内逐条改写：

| 现行条目 | 改为 |
|---|---|
| `- [ ] 各模块均可单独检出、单独安装依赖、单独启动，互不依赖其他模块的构建产物` | `- [ ] 各模块均可单独安装依赖、单独启动，互不依赖其他模块的构建产物` |
| `- [ ] 任一模块重新构建/发版，不触发也不破坏其他模块` | 保留不变 |
| `- [ ] 任一模块的源码中不含对其他模块的 import / 路径引用 / 构建期依赖` | 保留不变 |
| `- [ ] 服务端不可用时，Web 能正常启动并给出降级提示，不崩溃` | 保留不变 |
| `- [ ] 服务端地址均为外部配置项，代码中无硬编码地址` | 保留不变 |
| `- [ ] 各模块可独立版本化发布；服务端小版本升级不强制客户端同步发版` | `- [ ] 各模块可独立构建与发布（独立产物、独立版本号）；服务端小版本升级不强制客户端同步发版` |
| 其余小程序端条目 | 保留不变 |

- [ ] **Step 8: 改 §13 决策表**

决策表第 1 行「影响」列末段：

```
独立仓库，满足模块独立性
```

改为：

```
仓外独立仓库，满足模块边界
```

决策表第 6 行**整行**替换：

```markdown
| 6 | 仓库形态     | **单仓三模块目录**，模块边界保留（小程序端为仓外独立仓库）      | 各模块独立依赖、独立构建与发布；本仓库为唯一代码来源            |
```

- [ ] **Step 9: 改 §13.1 决策 6 衍生**

```markdown
- **决策 6 衍生**：各模块拆分独立仓库后，接口契约需有唯一权威来源；
  本文档（第 7 节接口清单）即为契约基线，各仓库以其为准。
```

改为：

```markdown
- **决策 6 衍生**：三个模块合并到单仓后，接口契约仍需唯一权威来源；
  本文档（第 7 节接口清单）即为契约基线，各模块以其为准。
```

- [ ] **Step 10: 全文扫描残留**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "聚合检出\|聚合仓库\|第四个独立仓库\|独立 git 仓库\|非 monorepo\|拆分独立仓库\|各仓库以其为准" zg-homework-docs/sys_doc/PRD.md
```

Expected: 无输出。

若命中，逐条按上表判断是否为遗漏项并修正。

- [ ] **Step 11: 确认版本号一致**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "v2\.2\|v2\.3" zg-homework-docs/sys_doc/PRD.md | head -10
```

Expected: 标题为 `v2.3`；§0 变更记录含 `### v2.3（单一仓库化）`；§0 里 v2.2 的历史条目保留（那是历史记录，不该删）。其它正文若引用 PRD 版本号，同步改为 v2.3。

- [ ] **Step 12: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-docs/sys_doc/PRD.md
git commit -m "docs(prd): PRD 升 v2.3，决策 6 改为单仓三模块目录

仓库形态从「拆分为独立仓库」改为「同一仓库的独立目录」，模块边界六条
原则保留。§2.2 / §2.2.1 / §2.2.2 / §9.6 / §11 / §12 / §13 / §13.1 同步。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: 更新 `小程序.md`

**Files:**
- Modify: `zg-tsp-docs/sys_doc/小程序.md`（改 4 处）

**Interfaces:**
- Consumes: Task 10 的 PRD v2.3 口径。
- Produces: 小程序端文档与单仓形态一致。

- [ ] **Step 1: 改文件头**

```markdown
> 代码位置：`/Users/zg/WeChatProjects/HomeworkPoints`（独立仓库，**不在本聚合检出内**）
> 上游契约：`zg-tsp-docs/sys_doc/PRD.md` v2.2；实现口径以 `zg-tsp-server/app/` 为准
```

改为：

```markdown
> 代码位置：`/Users/zg/WeChatProjects/HomeworkPoints`（仓外独立仓库，**不在本检出内**）
> 上游契约：`zg-tsp-docs/sys_doc/PRD.md` v2.3；实现口径以 `zg-tsp-server/app/` 为准
```

- [ ] **Step 2: 改「仓库归属」决策行**

```markdown
| 仓库归属 | **独立仓库，放在聚合检出外** | 不改动现有三仓结构与 `split_repos.sh`；小程序本身是独立发布单元，构建/审核节奏与其它端不同 |
```

改为：

```markdown
| 仓库归属 | **仓外独立仓库** | 小程序本身是独立发布单元，构建/审核节奏与其它端不同；工具链（微信开发者工具）与 Python/Node 不兼容，故不并入主仓库 |
```

- [ ] **Step 3: 改 §11「与本仓库的关系」**

```markdown
## 11. 与本仓库的关系

小程序代码**在本聚合检出之外**（`/Users/zg/WeChatProjects/HomeworkPoints`，独立 git 仓库）。

- 本文件（`zg-tsp-docs/sys_doc/小程序.md`）是它唯一的规划文档与契约索引
- 服务端契约变更时，**须同步更新本文件的 §5.4 接口调用面与 §7 技术对策**
- 小程序代码变更**不影响** `scripts/dev.sh` / `split_repos.sh`（那两个脚本只处理三个模块）
- 建议在小程序仓库根目录放一份 `README.md`，指向本规划文档与服务端契约入口
```

改为：

```markdown
## 11. 与主仓库的关系

小程序代码**在主仓库之外**（`/Users/zg/WeChatProjects/HomeworkPoints`，独立 git 仓库）。

- 本文件（`zg-tsp-docs/sys_doc/小程序.md`）是它唯一的规划文档与契约索引
- 服务端契约变更时，**须同步更新本文件的 §5.4 接口调用面与 §7 技术对策**
- 小程序代码变更**不影响** `scripts/dev.sh`（该脚本只处理主仓库内的服务端与 Web 端）
- 建议在小程序仓库根目录放一份 `README.md`，指向本规划文档与服务端契约入口
```

- [ ] **Step 4: 改「代码位置」表格行**

```markdown
| 代码位置 | `/Users/zg/WeChatProjects/HomeworkPoints` | 独立 git 仓库 |
```

改为：

```markdown
| 代码位置 | `/Users/zg/WeChatProjects/HomeworkPoints` | 仓外独立 git 仓库 |
```

- [ ] **Step 5: 扫描残留**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -n "聚合检出\|三仓\|split_repos\|聚合仓库" zg-homework-docs/sys_doc/小程序.md
```

Expected: 无输出。

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git add zg-homework-docs/sys_doc/小程序.md
git commit -m "docs(小程序): 同步单仓库形态措辞

仓库归属决策改为「仓外独立仓库」，删除对 split_repos.sh 与三仓结构的引用。

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: 删除五个 `split/*` 分支与 `../zg-tsp-repos/`

**Files:**
- Delete: git 分支 `split/zg-tsp-server`、`split/zg-tsp-web`、`split/zg-tsp-docs`、`split/zg-tsp-android`、`split/zg-tsp-ios`（共 **5** 个分支）
- Delete: 目录 `../zg-tsp-repos/`（整个目录）

**Interfaces:**
- Consumes: Task 1 打的归档 tag `archive/pre-merge-2026-11-12`；Task 6 删除的 `scripts/split_repos.sh`。
- Produces: 仓库只剩 `main` 与 `archive/pre-merge-2026-11-12` 两个分支；工作区外不再有独立检出。

- [ ] **Step 1: 再次确认三个独立检出无未提交改动**（删除前最后一道闸）

```bash
cd /Users/zg/PycharmProjects/zg-homework
for d in ../zg-homework-repos/*/; do
  echo "=== $d"
  git -C "$d" status --porcelain
done
```

Expected: 三段 `===`，其后**无任何输出**。

**若任一段有输出：立即停止本任务**，把输出报告给用户，不要继续删除。

- [ ] **Step 2: 确认归档 tag 存在且指向合并前基线**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git rev-parse archive/pre-merge-2026-11-12
git log --oneline -1 archive/pre-merge-2026-11-12
```

Expected: 第二行输出 `bfb8935 docs(spec): 修正设计文档 —— PRD 章节号纠错与验收标准改写补齐`。

- [ ] **Step 3: 列出待删分支**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git branch --list 'split/*'
```

Expected: 恰好 5 行：

```
  split/zg-tsp-android
  split/zg-tsp-docs
  split/zg-tsp-ios
  split/zg-tsp-server
  split/zg-tsp-web
```

若数量或名字与预期不符，**停止**并报告。

- [ ] **Step 4: 删除五个分支**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git branch -D split/zg-homework-server split/zg-homework-web split/zg-homework-docs \
                split/zg-homework-android split/zg-homework-ios
```

Expected: 每行 `Deleted branch split/... (was <sha>)`。

- [ ] **Step 5: 确认分支已删**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git branch --list 'split/*'
git branch -a
```

Expected: 第一条无输出；第二条只剩 `* main` 与 `archive/pre-merge-2026-11-12`。

- [ ] **Step 6: 删除 `../zg-tsp-repos/` 目录**

```bash
ls -la ../zg-homework-repos/
rm -rf ../zg-homework-repos/
ls -d ../zg-homework-repos 2>&1
```

Expected: 最后一行 `ls: ../zg-tsp-repos: No such file or directory`（退出码非 0，属预期）。

> `rm -rf` 不可逆 —— Step 1 的检查与 Step 2 的归档 tag 是仅有的兜底。**确认 Step 1 无未提交改动后再执行。**

- [ ] **Step 7: 确认 `main` 历史仍完整**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git log --oneline | wc -l
git log --oneline -3
```

Expected: 提交数 **不少于** 合并前的数量（本计划执行前为 18 条），且最新 3 条是 Task 11 的提交。

- [ ] **Step 8: 提交归档 tag**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git tag -a archive/pre-merge-2026-11-12 -m "单一仓库化合并前的基线存档" 2>/dev/null || echo "tag 已存在，跳过"
git tag -l
```

Expected: `archive/pre-merge-2026-11-12` 与 `main`。

---

## Task 13: 端到端验证

**Files:**
- 无文件改动（只验证）

**Interfaces:**
- Consumes: 全部前置任务。
- Produces: 一份验证结论；若发现回归，在本任务内定位并修复。

- [ ] **Step 1: 全仓扫描残留引用**

```bash
cd /Users/zg/PycharmProjects/zg-homework
grep -rn "split_repos\|zg-tsp-repos\|聚合检出\|聚合仓库\|第四个独立仓库\|独立 git 仓库" . \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=superpowers --exclude-dir=docs --exclude-dir=dist
```

Expected: **无输出**。

若有输出，逐条判断：属于「已废弃」的历史说明可保留；属于会误导读者的现行表述必须改。

另需单独确认两个**已核对为干净**的文件（实施时复核一次即可）：

```bash
grep -n "仓库\|聚合\|独立仓库" zg-homework-docs/sys_doc/config.md zg-homework-docs/sys_doc/迭代.md
```

Expected: 无输出（这两个文件不含仓库形态表述，无需改动）。

- [ ] **Step 2: 模块边界检查**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make check 2>&1 | tail -30
```

Expected: `=== 独立性检查：8/8 通过 ===`（或「模块边界检查：8/8 通过」），随后 `acceptance_check.py` 输出各条 ✓。

`acceptance_check.py` 需要服务端已启动 —— 若报连接错误，先 `make server` 再重跑。

若 `acceptance_check.py` 报 admin 登录失败，检查 `ACCEPTANCE_ADMIN_PASSWORD` 是否已设置。

- [ ] **Step 3: 服务端可启动**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make server
sleep 3
curl -s -X POST http://127.0.0.1:8000/homework_api/health
```

Expected: `{"code":0,"message":"ok","data":{"status":"ok","env":"..."}}`

- [ ] **Step 4: Web 可构建**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make build 2>&1 | tail -8
```

Expected: `✓ built in ...`，退出码 0。

- [ ] **Step 5: 两端可联调**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make web
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5173/homework_api/health
```

Expected: 第一行 `200`（SPA 首页）；第二行 `200`（代理保留前缀，未 404）。

- [ ] **Step 6: 停止全部**

```bash
cd /Users/zg/PycharmProjects/zg-homework
make stop
sleep 1
make status
```

Expected: `status` 显示两个模块均「未运行」。

- [ ] **Step 7: 确认工作区干净**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git status --short
```

Expected: 只剩 Task 1 记录过的那些**未跟踪**文件（`zg-tsp-server/deploy/`、`zg-tsp-web/src/pages/parent/*.tsx` 等），**无已跟踪文件的改动**。

- [ ] **Step 8: 记录验证结论**

```bash
cd /Users/zg/PycharmProjects/zg-homework
git log --oneline -12
```

Expected: 11 条本次提交（Task 2-11）+ 2 条 spec 提交。

把本任务各步的实际输出汇总报告给用户。若有任何一步未通过，**不要声称完成** —— 先修复再报告。

---

## 回滚指引

任一环节出问题，按以下顺序回滚：

```bash
cd /Users/zg/PycharmProjects/zg-homework

# 1. 回到合并前的基线
git reset --hard archive/pre-merge-2026-11-12

# 2. 恢复被删的 split 分支（对象仍在 reflog / tag 里）
git branch split/zg-homework-server archive/pre-merge-2026-11-12
# …其余分支同理

# 3. 恢复独立检出（若已删）
git clone -b split/zg-homework-server /Users/zg/PycharmProjects/zg-homework ../zg-homework-repos/zg-homework-server
```

注意：`git reset --hard` 会丢弃工作区改动，执行前先确认无需要保留的内容。
