#!/bin/sh
# zg-tsp 一键启动脚本
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
#   REPOS_DIR   代码目录（默认脚本所在仓库；显式指定时必须含 zg-tsp-server 与 zg-tsp-web）
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
