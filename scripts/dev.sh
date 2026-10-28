#!/usr/bin/env bash
# zg-tsp 一键启动脚本
#
# 用法：
#   ./scripts/dev.sh              # 启动 server + web（默认）
#   ./scripts/dev.sh server       # 只启动服务端
#   ./scripts/dev.sh web          # 只启动 Web 端
#   ./scripts/dev.sh ios          # 启动 iOS 端（需 Xcode + 已连接设备或模拟器）
#   ./scripts/dev.sh android      # 启动 Android 端（需 Android SDK + 设备/模拟器）
#   ./scripts/dev.sh all          # 启动全部
#   ./scripts/dev.sh stop         # 停止本脚本启动的所有进程
#   ./scripts/dev.sh status       # 查看各模块运行状态
#   ./scripts/dev.sh logs         # 跟随查看日志
#
# 环境变量：
#   REPOS_DIR   五个仓库所在目录（默认自动探测）
#   SERVER_PORT 服务端端口（默认 8000）
#   WEB_PORT    Web 端端口（默认 5173）
#   API_TARGET  Web 端代理指向的服务端地址（默认 http://127.0.0.1:$SERVER_PORT）
#   VENV_PY     服务端 Python 解释器（默认 $REPOS_DIR/../zg-tsp/.venv/bin/python）
#   DEVICE_ID   移动端设备 ID（默认自动探测真机/模拟器）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- 定位仓库目录 ---
find_repos_dir() {
  local candidates=(
    "${REPOS_DIR:-}"
    "${ROOT}/../zg-tsp-repos"
    "${ROOT}"
    "${HOME}/zg-tsp-repos"
  )
  for d in "${candidates[@]}"; do
    [ -n "$d" ] || continue
    if [ -d "$d/zg-tsp-server" ] && [ -d "$d/zg-tsp-web" ]; then
      echo "$d"
      return 0
    fi
  done
  return 1
}

REPOS_DIR="$(find_repos_dir || true)"
if [ -z "$REPOS_DIR" ]; then
  echo "✗ 找不到五个仓库目录。"
  echo "  请设置 REPOS_DIR 环境变量，或确保 zg-tsp-server 与 zg-tsp-web 同级存在。"
  exit 1
fi
REPOS_DIR="$(cd "$REPOS_DIR" && pwd)"

SERVER_PORT="${SERVER_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
API_TARGET="${API_TARGET:-http://127.0.0.1:${SERVER_PORT}}"
LOG_DIR="${LOG_DIR:-${ROOT}/.dev-logs}"
PID_FILE="${LOG_DIR}/dev.pids"

# --- 颜色 ---
if [ -t 1 ]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;36m'; N=$'\033[0m'
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
  ( cd "$dir" && exec "$@" ) > "${LOG_DIR}/${name}.log" 2>&1 &
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
  # 代理目标通过环境变量注入，不改动仓库内文件
  VITE_PROXY_TARGET="${API_TARGET}" \
    start_bg web "${REPOS_DIR}/zg-tsp-web" npm run dev -- --port "${WEB_PORT}"
  wait_for_port "${WEB_PORT}" 25 "Web 端" || return 1
}

# 判断一个目录是否是「可用的 Android SDK 根目录」。
#
# Flutter 自己的判据很宽松（存在 platform-tools 或 licenses 就算），
# 会误判 Homebrew 的 android-platform-tools cask 目录——它只有 adb，
# 没有 platforms/ build-tools/ ndk/。这里要求 platforms/ 或 build-tools/。
is_sdk_root() {
  local d="$1"
  [ -d "$d" ] || return 1
  [ -d "${d}/platforms" ] || [ -d "${d}/build-tools" ] || return 1
  return 0
}

# 查找 Android SDK 根目录：环境变量 → local.properties 的 sdk.dir → 常见位置。
android_sdk_dir() {
  local d props sdk_dir
  for d in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}"; do
    [ -n "$d" ] || continue
    if is_sdk_root "$d"; then echo "$d"; return 0; fi
  done

  props="${REPOS_DIR:-}/zg-tsp-android/android/local.properties"
  if [ -f "$props" ]; then
    sdk_dir="$(sed -n 's/^[[:space:]]*sdk\.dir[[:space:]]*=[[:space:]]*\(.*\)$/\1/p' "$props" | head -1 | sed 's/[[:space:]]*$//')"
    if [ -n "$sdk_dir" ] && is_sdk_root "$sdk_dir"; then
      echo "$sdk_dir"; return 0
    fi
  fi

  for d in "${HOME}/Library/Android/sdk" "${HOME}/Android/Sdk" \
           "/opt/homebrew/share/android-commandlinetools" \
           "/usr/local/share/android-commandlinetools"; do
    [ -n "$d" ] || continue
    if is_sdk_root "$d"; then echo "$d"; return 0; fi
  done
  return 1
}

flutter_device_id() {
  # $1=平台（ios/android）
  # `flutter run -d` 需要真实设备 ID，平台名（ios/android）并不被接受，
  # 这里从 `flutter devices --machine` 中挑一个匹配该平台的设备。
  local plat="$1"
  flutter devices --machine 2>/dev/null | python3 -c '
import json, sys
plat = sys.argv[1]
want = {"ios": ("ios", "darwin"), "android": ("android",)}[plat]
try:
    devs = json.load(sys.stdin)
except Exception:
    sys.exit(1)
# 优先真机（deviceType 为 device），其次模拟器
for kind in ("device", "simulator"):
    for d in devs:
        if d.get("targetPlatform") not in want:
            continue
        if d.get("deviceType") != kind:
            continue
        # 跳过无头浏览器等非移动目标
        if d.get("targetPlatform") in ("web-javascript", "darwin"):
            continue
        print(d["id"])
        sys.exit(0)
sys.exit(1)
' "$plat" 2>/dev/null
}

start_mobile() {
  local plat="$1" dir="${REPOS_DIR}/zg-tsp-$1"
  info "启动 ${plat} 端 zg-tsp-${plat}"
  if ! command -v flutter >/dev/null 2>&1; then
    err "找不到 flutter"; return 1
  fi
  if [ "$plat" = "ios" ] && ! xcode-select -p >/dev/null 2>&1; then
    warn "iOS 构建需要完整 Xcode（当前仅 Command Line Tools），跳过"
    return 0
  fi
  if [ "$plat" = "android" ] && [ -z "$(android_sdk_dir || true)" ]; then
    warn "未检测到 Android SDK，跳过"; return 0
  fi
  [ -d "$dir" ] || { err "找不到 $dir"; return 1; }
  ( cd "$dir" && flutter pub get ) > "${LOG_DIR}/${plat}-pubget.log" 2>&1 \
    || { err "flutter pub get 失败"; return 1; }

  # 解析可用设备 ID：优先真机，无真机则起模拟器
  local device_id
  device_id="$(flutter_device_id "$plat" || true)"
  local args=()
  # DEVICE_ID 显式指定时优先采用，跳过自动探测
  if [ -n "${DEVICE_ID:-}" ]; then
    device_id="$DEVICE_ID"
  fi
  if [ -n "$device_id" ]; then
    ok "使用设备：${device_id}"
    args=(-d "$device_id")
  else
    # 没有已连接设备，尝试拉起一个模拟器
    local emu
    emu="$(flutter emulators --machine 2>/dev/null | python3 -c '
import json, sys
plat = sys.argv[1]
try:
    emus = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for e in emus:
    name = (e.get("name") or "").lower()
    if plat == "ios" and ("ios" in name or "iphone" in name or "ipad" in name):
        print(e["name"]); sys.exit(0)
    if plat == "android" and ("android" in name or "pixel" in name or "emulator" in name):
        print(e["name"]); sys.exit(0)
sys.exit(1)
' "$plat" 2>/dev/null || true)"
    if [ -n "$emu" ]; then
      warn "未检测到已连接设备，启动模拟器：${emu}"
      ( cd "$dir" && flutter emulators --launch "$emu" ) >/dev/null 2>&1 || true
      # 等模拟器就绪
      local i=0
      while [ $i -lt 30 ]; do
        device_id="$(flutter_device_id "$plat" || true)"
        [ -n "$device_id" ] && break
        sleep 2; i=$((i + 1))
      done
    fi
    if [ -z "$device_id" ]; then
      warn "未找到可用的 ${plat} 设备或模拟器，跳过。"
      echo "      启动模拟器：flutter emulators   或连接真机后重试"
      echo "      也可用 DEVICE_ID 环境变量指定：DEVICE_ID=<id> $0 ${plat}"
      return 0
    fi
    ok "使用设备：${device_id}"
    args=(-d "$device_id")
  fi

  # 移动端 API 走构建期注入
  local define="--dart-define=API_BASE_URL=${API_TARGET}"

  # Android：显式指定 SDK 根目录。
  # Flutter 探测 Android SDK 的判据很宽松（存在 platform-tools 或 licenses
  # 即算有效），在装了 Homebrew android-platform-tools cask 的机器上会误判成
  # cask 目录——那里只有 adb，没有 platforms/ build-tools/ ndk/，
  # Gradle 用它当 SDK 根会在装 NDK 时报 "licences have not been accepted"。
  # 导出正确的 ANDROID_HOME 可让 Gradle 与 Flutter 指向同一个目录。
  #
  # 注意：不能用 `ANDROID_HOME=x exec flutter ...` —— start_bg 里是
  # `exec "$@"`，前置环境赋值会被当成可执行文件名。这里改用 env 命令。
  local env_prefix=()
  if [ "$plat" = "android" ]; then
    local sdk_root
    sdk_root="$(android_sdk_dir || true)"
    if [ -n "$sdk_root" ]; then
      env_prefix=(env "ANDROID_HOME=$sdk_root" "ANDROID_SDK_ROOT=$sdk_root")
    fi
  fi

  start_bg "${plat}" "$dir" "${env_prefix[@]}" flutter run "${args[@]}" "$define"
  warn "${plat} 端正在启动，首次编译较慢，请查看日志：${LOG_DIR}/${plat}.log"
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
      port_busy "${port}" || break
      sleep 0.3
    done
    if port_busy "${port}"; then
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
  # 移动端无端口，只能靠 PID 记录判断进程是否存活；
  # 仅凭日志文件存在会误报（进程早已退出但日志文件还在）。
  for plat in ios android; do
    local pid=""
    if [ -f "$PID_FILE" ]; then
      pid="$(awk -v n="$plat" '$1 == n { print $2 }' "$PID_FILE" 2>/dev/null || true)"
    fi
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      printf "  %-22s %-8s %s\n" "${plat} 端" "-" "${G}运行中${N} (pid ${pid})"
    elif [ -f "${LOG_DIR}/${plat}.log" ]; then
      printf "  %-22s %-8s %s\n" "${plat} 端" "-" "未运行（日志见 ${LOG_DIR}/${plat}.log）"
    fi
  done
  echo
  info "日志目录：${LOG_DIR}"
  ls -1 "${LOG_DIR}" 2>/dev/null | sed 's/^/      /'
}

tail_logs() {
  [ -d "$LOG_DIR" ] || { warn "还没有日志目录"; return 0; }
  # 用数组收集，避免文件名含空格时被拆成多个参数
  local files=()
  while IFS= read -r f; do
    [ -n "$f" ] && files+=("$f")
  done < <(ls -1 "${LOG_DIR}"/*.log 2>/dev/null || true)
  [ ${#files[@]} -gt 0 ] || { warn "暂无日志"; return 0; }
  tail -f "${files[@]}"
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
  ios)     start_mobile ios ;;
  android) start_mobile android ;;
  all)
    start_server && start_web
    ;;
  stop)    stop_all ;;
  status)  show_status ;;
  logs)    tail_logs ;;
  ""|"start")
    start_server && start_web
    ;;
  *)
    err "未知命令：$1"
    echo "用法：$0 {start|server|web|ios|android|all|stop|status|logs}"
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
  # /health 是 POST-only 路由，直接用浏览器打开会返回 405
  echo "  服务端： curl -X POST ${API_TARGET}/health"
  echo
fi
