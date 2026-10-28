#!/usr/bin/env bash
# zg-tsp 移动端一键打包脚本
#
# 用法：
#   ./scripts/build.sh ios dev            # iOS 测试渠道（ipa）
#   ./scripts/build.sh ios prod           # iOS 生产渠道（ipa）
#   ./scripts/build.sh android dev        # Android 测试渠道（apk）
#   ./scripts/build.sh android prod       # Android 生产渠道（aab）
#   ./scripts/build.sh ios                # 渠道缺省为 dev
#   ./scripts/build.sh --check            # 只做环境预检，不打包
#   ./scripts/build.sh --help
#
# 环境变量：
#   REPOS_DIR       五个仓库所在目录（默认自动探测）
#   API_BASE_URL    产物内写入的服务端基地址
#                   默认：dev → http://127.0.0.1:8000
#                         prod → https://api.example.com
#   BUILD_OUTPUT_DIR 产物归档目录（默认 $ROOT/dist）
#   VERSION         覆盖产物版本号（默认取 pubspec.yaml 的 version）
#
# 说明：
#   渠道（flavor）在 Flutter 侧通过 --dart-define=FLAVOR 与 --flavor 双重表达：
#   - FLAVOR 决定 AppConfig.flavor（dev/prod），影响运行时行为
#   - --flavor 决定 Android 的 productFlavors 与 iOS 的 Scheme/BuildConfiguration
#   工程若尚未配置对应渠道，脚本会自动补齐（详见 ensure_*_flavor）。

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

BUILD_OUTPUT_DIR="${BUILD_OUTPUT_DIR:-${ROOT}/dist}"
LOG_DIR="${ROOT}/.dev-logs"

# --- 颜色 ---
if [ -t 1 ]; then
  R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[0;33m'; B=$'\033[0;36m'; N=$'\033[0m'
else
  R=""; G=""; Y=""; B=""; N=""
fi

info() { echo "${B}==>${N} $*"; }
ok()   { echo "  ${G}✓${N} $*"; }
warn() { echo "  ${Y}!${N} $*"; }
err()  { echo "  ${R}✗${N} $*" >&2; }
step() { echo "  ${B}·${N} $*"; }

# 首字母大写（dev → Dev）。
# 不用 ${var^}：那是 bash 4.0+ 的语法，而 macOS 自带 bash 3.2，
# 会在运行时直接报 "bad substitution" 而退出。
upper_first() {
  printf '%s' "$(printf '%s' "$1" | cut -c1 | tr '[:lower:]' '[:upper:]')$(printf '%s' "$1" | cut -c2-)"
}

usage() {
  cat <<'EOF'
zg-tsp 移动端一键打包

用法：
  ./scripts/build.sh ios [dev|prod]        打包 iOS（ipa）
  ./scripts/build.sh android [dev|prod]     打包 Android（dev→apk，prod→aab）
  ./scripts/build.sh --check                仅做环境预检
  ./scripts/build.sh --help                 显示本帮助

环境变量：
  REPOS_DIR         仓库目录（默认自动探测 ../zg-tsp-repos）
  API_BASE_URL      服务端基地址
                    dev  默认 http://127.0.0.1:8000
                    prod 默认 https://api.example.com
  BUILD_OUTPUT_DIR  产物归档目录（默认 $ROOT/dist）
  VERSION           覆盖版本号（默认取 pubspec.yaml）

示例：
  API_BASE_URL=https://test.example.com ./scripts/build.sh ios dev
  API_BASE_URL=https://api.example.com  ./scripts/build.sh android prod

环境安装教程见 zg-tsp-docs/sys_doc/ENV_SETUP.md
EOF
}

# --- 环境预检 ---

# 检查项计数：失败项汇总后统一退出
CHECK_FAILED=0

check_ok()   { ok "$1"; }
check_fail() { err "$1"; CHECK_FAILED=$((CHECK_FAILED + 1)); }

check_flutter() {
  if ! command -v flutter >/dev/null 2>&1; then
    check_fail "未安装 Flutter"
    echo "      安装：brew install --cask flutter"
    return
  fi
  local ver
  ver="$(flutter --version 2>/dev/null | head -1 | sed 's/^Flutter //')"
  check_ok "Flutter ${ver:-已安装}"
}

check_xcode() {
  if ! xcode-select -p >/dev/null 2>&1; then
    check_fail "未安装 Xcode 命令行工具"
    echo "      安装：xcode-select --install"
    return
  fi
  # 完整 Xcode 才带 xcodebuild；仅 CLT 时 xcode-select -p 指向 CommandLineTools
  if ! xcodebuild -version >/dev/null 2>&1; then
    check_fail "缺少完整 Xcode（当前仅 Command Line Tools，无法打包 iOS）"
    echo "      安装：App Store 安装 Xcode（需 ≥ 15），然后依次执行："
    echo "        sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
    echo "        sudo xcodebuild -runFirstLaunch"
    echo "      详见：zg-tsp-docs/sys_doc/ENV_SETUP.md 第 2 节"
    return
  fi
  local ver
  ver="$(xcodebuild -version 2>/dev/null | head -1)"
  check_ok "${ver:-Xcode 已安装}"
}

check_cocoapods() {
  if ! command -v pod >/dev/null 2>&1; then
    check_fail "未安装 CocoaPods"
    echo "      安装：brew install cocoapods"
    echo "      提示：不要用 sudo gem install（macOS 系统 Ruby 2.6 权限受限，易失败）"
    return
  fi
  check_ok "CocoaPods $(pod --version 2>/dev/null || echo '已安装')"
}

# 判断一个目录是否是「可用的 Android SDK 根目录」。
#
# Flutter 自己的判据很宽松（存在 platform-tools 或 licenses 就算），
# 见 android_sdk.dart 的 validSdkDirectory()。这会误判 Homebrew 的
# android-platform-tools cask 目录——它只有 adb，没有 platforms/
# build-tools/ndk/，Gradle 用它当 SDK 根就会报
#   "Failed to install the following Android SDK packages..."
# 因此这里要求存在 platforms/ 或 build-tools/，与 Gradle 的实际需要一致。
is_sdk_root() {
  local d="$1"
  [ -d "$d" ] || return 1
  [ -d "${d}/platforms" ] || [ -d "${d}/build-tools" ] || return 1
  return 0
}

# 候选 SDK 目录，按优先级排列：
#   1) ANDROID_HOME / ANDROID_SDK_ROOT 环境变量
#   2) 移动端仓库 android/local.properties 里的 sdk.dir
#      —— Gradle 实际用的就是这个值，最权威
#   3) 常见安装位置：
#      - ~/Library/Android/sdk        （Android Studio 默认）
#      - ~/Android/Sdk                （Linux 常见）
#      - /opt/homebrew/share/android-commandlinetools
#        （brew install --cask android-commandlinetools 的 SDK 根目录）
android_sdk_dir() {
  local d props sdk_dir
  for d in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}"; do
    [ -n "$d" ] || continue
    if is_sdk_root "$d"; then
      echo "$d"
      return 0
    fi
  done

  props="${REPOS_DIR:-}/zg-tsp-android/android/local.properties"
  if [ -f "$props" ]; then
    sdk_dir="$(sed -n 's/^[[:space:]]*sdk\.dir[[:space:]]*=[[:space:]]*\(.*\)$/\1/p' "$props" | head -1 | sed 's/[[:space:]]*$//')"
    if [ -n "$sdk_dir" ]; then
      # Windows 风格的路径在 macOS 上不适用，这里只处理 POSIX 路径
      sdk_dir="${sdk_dir//\\/:}"
      if is_sdk_root "$sdk_dir"; then
        echo "$sdk_dir"
        return 0
      fi
    fi
  fi

  for d in "${HOME}/Library/Android/sdk" "${HOME}/Android/Sdk" \
           "/opt/homebrew/share/android-commandlinetools" \
           "/usr/local/share/android-commandlinetools"; do
    [ -n "$d" ] || continue
    if is_sdk_root "$d"; then
      echo "$d"
      return 0
    fi
  done
  return 1
}

check_android_sdk() {
  local d
  d="$(android_sdk_dir || true)"
  if [ -z "$d" ]; then
    check_fail "未检测到 Android SDK"
    echo "      安装：brew install --cask android-commandlinetools"
    echo "      或设置 ANDROID_HOME 环境变量指向 SDK 目录"
    return
  fi
  check_ok "Android SDK：${d}"
  if [ -x "${d}/platform-tools/adb" ]; then
    check_ok "adb 已就绪"
  else
    warn "未找到 adb（${d}/platform-tools），USB 调试设备将不可用"
  fi
  check_android_platform "$d"
}

# 检查编译所需的 Android platform 是否已安装。
#
# Flutter 3.47 默认 compileSdk = 36，但 SDK 里可能只装了 android-35。
# 缺失时 AGP 会在构建过程中自动下载（需要网络与已接受的 licenses），
# 这里先给出提示，避免构建到一半才失败。
check_android_platform() {
  local d="$1"
  local want have=""
  want="$(flutter_compile_sdk || true)"
  [ -n "$want" ] || return 0

  if [ -d "${d}/platforms/android-${want}" ]; then
    check_ok "Android platform android-${want} 已安装"
    return 0
  fi

  # 列出已装的 platform，便于对照
  if [ -d "${d}/platforms" ]; then
    have="$(ls "${d}/platforms" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  fi

  warn "未找到 Android platform android-${want}（已安装：${have:-无}）"
  step "构建时 AGP 会尝试自动下载；如失败请手动安装："
  echo "      sdkmanager \"platforms;android-${want}\""
  echo "      或：yes | sdkmanager --licenses"
}

# 解析 Flutter 实际用于 Android 构建的 JDK。
#
# Flutter 的查找顺序（见 flutter_tools/lib/src/android/java.dart）：
#   1) flutter config --jdk-dir 指定的目录
#   2) JAVA_HOME 环境变量
#   3) PATH 上的 java
# 所以不能只看系统 `java`——它可能与打包用的 JDK 不是同一个。
# 这也正是「系统用 JDK 1.8 开发、打包用 JDK 17」这类共存场景的关键。
#
# `flutter config --jdk-dir` 只能写、不能读（不带值会报 Missing argument），
# 因此从 Flutter 的配置文件里读：
#   macOS/Linux: $XDG_CONFIG_HOME/flutter/settings（默认 ~/.config/flutter/settings）
#   兜底: ~/.flutter_settings
flutter_configured_jdk() {
  local file value
  for file in "${XDG_CONFIG_HOME:-$HOME/.config}/flutter/settings" "$HOME/.flutter_settings"; do
    [ -f "$file" ] || continue
    value="$(sed -n 's/.*"jdk-dir"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$file" | head -1)"
    if [ -n "$value" ]; then
      echo "$value"
      return 0
    fi
  done
  return 1
}

flutter_java_home() {
  local configured
  configured="$(flutter_configured_jdk || true)"
  if [ -n "$configured" ] && [ -x "${configured}/bin/java" ]; then
    echo "$configured"
    return 0
  fi
  if [ -n "${JAVA_HOME:-}" ] && [ -x "${JAVA_HOME}/bin/java" ]; then
    echo "$JAVA_HOME"
    return 0
  fi
  if [ -x "/usr/libexec/java_home" ]; then
    local home
    home="$(/usr/libexec/java_home 2>/dev/null || true)"
    if [ -n "$home" ] && [ -x "${home}/bin/java" ]; then
      echo "$home"
      return 0
    fi
  fi
  local java_bin
  java_bin="$(command -v java 2>/dev/null || true)"
  if [ -n "$java_bin" ]; then
    echo "$(cd "$(dirname "$java_bin")/.." && pwd)"
    return 0
  fi
  return 1
}

check_java() {
  local home
  home="$(flutter_java_home || true)"
  if [ -z "$home" ] || [ ! -x "${home}/bin/java" ]; then
    check_fail "未找到 JDK（Android 构建需要 JDK 17+）"
    echo "      安装：brew install openjdk@17"
    echo "      指定给 Flutter："
    echo "        flutter config --jdk-dir=\"/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home\""
    return
  fi

  local ver
  ver="$("${home}/bin/java" -version 2>&1 | head -1 | sed 's/.*version "\([^"]*\)".*/\1/')"
  # Java 8 及以下写作 1.8.0_x；9 及以上写作 11 / 17 / 21
  local major="${ver%%.*}"
  [ "$major" = "1" ] && major="${ver#1.}" && major="${major%%.*}"
  case "$major" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$major" -lt 17 ]; then
        check_fail "打包用 JDK ${ver} 版本过低（AGP 9.x 需要 JDK 17+）"
        echo "      该 JDK：${home}"
        echo "      安装：brew install openjdk@17"
        echo "      指定给 Flutter（不影响系统 JAVA_HOME 与其它 Java 项目）："
        echo "        flutter config --jdk-dir=\"/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home\""
        return
      fi
      ;;
  esac
  ok "打包用 JDK ${ver:-已安装}：${home}"
}

# Android 签名：release 渠道需要 keystore
# 从 Flutter 工具链读取默认 compileSdk 版本。
#
# 权威来源是 FlutterExtension.kt 里的 val compileSdkVersion，
# 但读 Flutter 源码路径不够稳（不同安装方式路径不同），
# 因此先从 Gradle 插件目录找，找不到再退回已知默认值。
flutter_compile_sdk() {
  local root file val
  root="$(cd "$(dirname "$(command -v flutter 2>/dev/null || echo /nonexistent)")/.." 2>/dev/null && pwd || true)"
  [ -n "$root" ] && [ -d "$root" ] || return 0

  file="$(find "$root/packages/flutter_tools/gradle" -name "FlutterExtension.kt" 2>/dev/null | head -1 || true)"
  if [ -n "$file" ]; then
    val="$(sed -n 's/^[[:space:]]*val compileSdkVersion:[[:space:]]*Int[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$file" | head -1)"
    if [ -n "$val" ]; then
      echo "$val"
      return 0
    fi
  fi
  echo "36"
}

check_android_signing() {
  local dir="$1"
  local props="${dir}/android/key.properties"
  if [ -f "$props" ]; then
    check_ok "签名配置存在：${props}"
    return
  fi
  # 没有 key.properties 时 gradle 会退回 debug 签名，仅能出测试包
  warn "未找到 ${props}"
  step "release 渠道将使用 debug 签名（仅供内部测试，不可上架）"
  echo "      配置正式签名：创建 android/key.properties，写入 storeFile/storePassword/keyAlias/keyPassword"
}

check_ios_signing() {
  local dir="$1"
  local team
  # 没有匹配时 grep 返回 1，配合 set -o pipefail 会让整个管道返回 1，
  # 而命令替换在 set -e 下会直接终止脚本——所以必须显式兜底。
  team="$(grep -o 'DEVELOPMENT_TEAM = [A-Za-z0-9]*' "${dir}/ios/Runner.xcodeproj/project.pbxproj" 2>/dev/null | head -1 | awk '{print $3}' || true)"
  if [ -n "$team" ]; then
    check_ok "签名团队已配置（DEVELOPMENT_TEAM=${team}）"
  else
    warn "未检测到 DEVELOPMENT_TEAM，release 渠道可能无法签名"
    echo "      在 Xcode 中为 Runner target 配置 Signing Team 后重试"
  fi
}

# --- 渠道地址 ---

default_api_base_url() {
  case "$1" in
    prod) echo "https://api.example.com" ;;
    *)    echo "http://127.0.0.1:8000" ;;
  esac
}

# --- iOS 渠道自动配置 ---

# Flutter 的匹配规则（见 flutter_tools/ios/xcodeproj.dart）：
#   scheme 名 = flavor 首字母大写（dev → Dev）
#   build configuration 名 = <基础配置>-<scheme>（Release-Dev / Release-Prod）
# Scheme 文件名就是 scheme 名（xcscheme 内没有 name 属性，Xcode 取文件名），
# 因此需要同时补 Scheme 与 XCBuildConfiguration。
ensure_ios_flavor() {
  local dir="$1" flavor="$2"
  local scheme; scheme="$(upper_first "$flavor")"   # dev → Dev
  local proj="${dir}/ios/Runner.xcodeproj"
  local scheme_dir="${proj}/xcshareddata/xcschemes"
  local xcconfig="${dir}/ios/Flutter/${scheme}.xcconfig"

  # 已有 scheme 则认为渠道已配置
  if [ -f "${scheme_dir}/${scheme}.xcscheme" ]; then
    ok "iOS 渠道 ${scheme} 已配置"
    return 0
  fi

  info "补齐 iOS 渠道配置：${scheme}"

  # 1) xcconfig：渠道差异化配置（目前主要是 include Generated.xcconfig）
  if [ ! -f "$xcconfig" ]; then
    cat > "$xcconfig" <<EOF
// ${scheme} 渠道配置（由 scripts/build.sh 生成）
#include "Generated.xcconfig"
EOF
    ok "生成 ios/Flutter/${scheme}.xcconfig"
  fi

  # 2) pbxproj：新增 XCBuildConfiguration + XCConfigurationList
  python3 "$(dirname "${BASH_SOURCE[0]}")/lib/ios_flavor.py" \
    --project "${proj}/project.pbxproj" \
    --xcconfig "${scheme}.xcconfig" \
    --flavor "$flavor" \
    --scheme "$scheme" || {
      err "自动配置 iOS 渠道失败"
      return 1
    }
  ok "生成 ${scheme}.xcscheme 与对应构建配置"
}

# --- Android 渠道自动配置 ---

ensure_android_flavor() {
  local dir="$1" flavor="$2"
  local gradle="${dir}/android/app/build.gradle.kts"

  # 不在这里判断「是否已配置」就提前返回：
  # python 脚本自身是幂等的，且除注入 flavor 外还负责补齐
  # buildFeatures.resValues（AGP 9.x 默认关闭，不开会构建失败）。
  # 提前返回会导致这些修复被跳过。
  info "校验并补齐 Android 渠道配置：${flavor}"

  python3 "$(dirname "${BASH_SOURCE[0]}")/lib/android_flavor.py" \
    --gradle "$gradle" \
    --flavor "$flavor" || {
      err "自动配置 Android 渠道失败"
      return 1
    }
  ok "注入 productFlavors（dev / prod）"
}

# --- 构建 ---

# 从 pubspec.yaml 读版本号
pubspec_version() {
  local pubspec="$1"
  grep -m1 -E '^version:' "$pubspec" 2>/dev/null | sed 's/^version:[[:space:]]*//' | tr -d '"' || true
}

build_ios() {
  local dir="${REPOS_DIR}/zg-tsp-ios"
  local flavor="$1"
  local api="$2"
  local scheme; scheme="$(upper_first "$flavor")"

  [ -d "$dir" ] || { err "找不到 $dir"; return 1; }

  ensure_ios_flavor "$dir" "$flavor" || return 1

  info "构建 iOS ${flavor} 渠道（ipa）"
  local version="${VERSION:-$(pubspec_version "${dir}/pubspec.yaml")}"
  step "版本：${version:-未设置}"
  step "API：${api}"

  mkdir -p "$LOG_DIR"
  local log="${LOG_DIR}/build-ios-${flavor}.log"

  local args=(
    build ipa
    --flavor "$flavor"
    --dart-define="API_BASE_URL=${api}"
    --dart-define="FLAVOR=${flavor}"
  )
  [ -n "$version" ] && args+=(--build-name "$version")

  if ! ( cd "$dir" && flutter "${args[@]}" ) > "$log" 2>&1; then
    err "iOS 打包失败，日志：${log}"
    tail -n 20 "$log" | sed 's/^/      /'
    return 1
  fi
  ok "构建完成，日志：${log}"

  # 归档产物
  local found
  found="$(find "${dir}/build/ios" -name "*.ipa" -newermt "-30 minutes" 2>/dev/null | head -1 || true)"
  if [ -z "$found" ]; then
    found="$(find "${dir}/build" -name "*.ipa" 2>/dev/null | head -1 || true)"
  fi
  if [ -z "$found" ]; then
    warn "未找到 .ipa 产物，请查看日志：${log}"
    return 0
  fi
  archive_artifact "$found" "ios-${flavor}-${version:-build}.ipa"
}

build_android() {
  local dir="${REPOS_DIR}/zg-tsp-android"
  local flavor="$1"
  local api="$2"

  [ -d "$dir" ] || { err "找不到 $dir"; return 1; }

  ensure_android_flavor "$dir" "$flavor" || return 1

  info "构建 Android ${flavor} 渠道"
  local version="${VERSION:-$(pubspec_version "${dir}/pubspec.yaml")}"
  step "版本：${version:-未设置}"
  step "API：${api}"

  # 渠道决定产物类型：测试出 apk（可直装），生产出 aab（上架用）
  local target="apk"
  [ "$flavor" = "prod" ] && target="appbundle"

  mkdir -p "$LOG_DIR"
  local log="${LOG_DIR}/build-android-${flavor}.log"

  local args=(
    build "$target"
    --flavor "$flavor"
    --dart-define="API_BASE_URL=${api}"
    --dart-define="FLAVOR=${flavor}"
  )
  [ -n "$version" ] && args+=(--build-name "$version")

  # 显式指定 SDK 根目录。
  #
  # Flutter 探测 Android SDK 的判据很宽松（存在 platform-tools 或 licenses
  # 即算有效，见 android_sdk.dart 的 validSdkDirectory），在装了 Homebrew
  # android-platform-tools cask 的机器上会误判成
  #   /opt/homebrew/Caskroom/android-platform-tools/<ver>
  # 那个目录只有 adb，没有 platforms/ build-tools/ ndk/，
  # Gradle 用它当 SDK 根会在装 NDK 时报 "licences have not been accepted"。
  #
  # 而 Gradle 解析 SDK 根的优先级是 ANDROID_HOME > local.properties 的 sdk.dir，
  # 且 Flutter 会把自己探测到的路径通过 -Pflutter.androidSdkRoot 传给插件。
  # 导出正确的 ANDROID_HOME 可让三者指向同一个目录。
  local sdk_root
  sdk_root="$(android_sdk_dir || true)"
  if [ -z "$sdk_root" ]; then
    err "未找到可用的 Android SDK 根目录"
    return 1
  fi
  step "SDK：${sdk_root}"

  if ! ( cd "$dir" && ANDROID_HOME="$sdk_root" ANDROID_SDK_ROOT="$sdk_root" flutter "${args[@]}" ) > "$log" 2>&1; then
    err "Android 打包失败，日志：${log}"
    tail -n 20 "$log" | sed 's/^/      /'
    return 1
  fi
  ok "构建完成，日志：${log}"

  local ext="apk"
  [ "$target" = "appbundle" ] && ext="aab"
  local found
  found="$(find "${dir}/build" -name "*.${ext}" 2>/dev/null | head -1 || true)"
  if [ -z "$found" ]; then
    warn "未找到 .${ext} 产物，请查看日志：${log}"
    return 0
  fi
  archive_artifact "$found" "android-${flavor}-${version:-build}.${ext}"
}

archive_artifact() {
  local src="$1" name="$2"
  mkdir -p "$BUILD_OUTPUT_DIR"
  local dest="${BUILD_OUTPUT_DIR}/${name}"
  cp -f "$src" "$dest"
  local size
  size="$(du -h "$dest" | awk '{print $1}')"
  ok "产物：${dest}（${size}）"
}

# --- 主流程 ---

PLATFORM=""
FLAVOR=""
CHECK_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    ios|android) PLATFORM="$1"; shift ;;
    dev|prod)   FLAVOR="$1"; shift ;;
    --check)    CHECK_ONLY=1; shift ;;
    --help|-h)  usage; exit 0 ;;
    *)
      err "未知参数：$1"
      echo "用法：$0 {ios|android} [dev|prod] | --check | --help"
      exit 1
      ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  usage
  exit 1
fi
FLAVOR="${FLAVOR:-dev}"

API_BASE_URL="${API_BASE_URL:-$(default_api_base_url "$FLAVOR")}"

echo
info "zg-tsp 移动端打包 —— ${PLATFORM} / ${FLAVOR}"
echo

# --- 预检 ---
info "预检环境"
check_flutter
case "$PLATFORM" in
  ios)
    check_xcode
    check_cocoapods
    check_ios_signing "${REPOS_DIR}/zg-tsp-ios"
    ;;
  android)
    check_android_sdk
    check_java
    check_android_signing "${REPOS_DIR}/zg-tsp-android"
    ;;
esac

if [ "$CHECK_FAILED" -gt 0 ]; then
  echo
  err "预检未通过（${CHECK_FAILED} 项缺失），请先补齐上述依赖。"
  echo "      完整安装教程：zg-tsp-docs/sys_doc/ENV_SETUP.md"
  exit 1
fi
echo

if [ "$CHECK_ONLY" -eq 1 ]; then
  ok "预检通过，可以执行：$0 ${PLATFORM} ${FLAVOR}"
  exit 0
fi

# --- 构建 ---
case "$PLATFORM" in
  ios)     build_ios "$FLAVOR" "$API_BASE_URL" ;;
  android) build_android "$FLAVOR" "$API_BASE_URL" ;;
esac

echo
info "产物目录：${BUILD_OUTPUT_DIR}"
ls -1 "$BUILD_OUTPUT_DIR" 2>/dev/null | sed 's/^/      /'
echo
