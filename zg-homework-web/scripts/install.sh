#!/bin/sh
# 在共享 nginx 下安装本项目的前端片段与发布目录。
#
# 共享 nginx 的主配置、server 块与 TLS 证书由运维统一维护；
# 本脚本只写自己的片段 /etc/nginx/conf.d/zg-homework.conf 与 /var/lib/zg-homework-web。
# 片段内只允许 location 块：出现 server / events / http 块会与运维维护的配置冲突。
set -eu

ROOT_PREFIX=/
WEB_PREFIX=/homework/
API_PREFIX=/homework_api/
API_UPSTREAM=127.0.0.1:8000
DEPLOY_DIR=/var/lib/zg-homework-web
SNIPPET_FILE=/etc/nginx/conf.d/zg-homework.conf
NGINX_BIN=nginx
NGINX_MAIN_CONF=/etc/nginx/nginx.conf
NO_RELOAD=0
PRINT_ONLY=0

# 允许写入的路径是写死的：共享 nginx 的主配置、sites-available/、sites-enabled/
# 由运维统一维护，本项目只允许写自己的 conf.d 片段与自己的发布目录。
ALLOWED_SNIPPET_FILE=/etc/nginx/conf.d/zg-homework.conf
ALLOWED_DEPLOY_DIR=/var/lib/zg-homework-web

usage() {
    printf '%s\n' \
        '用法：sh scripts/install.sh [选项]' \
        '  --web-prefix PREFIX      前端路径前缀（默认 /homework/）' \
        '  --api-prefix PREFIX      后端路径前缀（默认 /homework_api/）' \
        '  --api-upstream HOST:PORT 后端上游（默认 127.0.0.1:8000，仅允许 127.0.0.1）' \
        "  --deploy-dir DIR         前端产物根目录（固定 ${ALLOWED_DEPLOY_DIR}）" \
        "  --snippet-file PATH      nginx 片段路径（固定 ${ALLOWED_SNIPPET_FILE}）" \
        '  --nginx-bin PATH         nginx 可执行文件（默认 nginx）' \
        '  --nginx-main-conf PATH   nginx 主配置路径（默认 /etc/nginx/nginx.conf）' \
        '  --root PREFIX            根前缀，用于沙箱测试（默认 /，必须是绝对路径）' \
        '  --no-reload              不 reload nginx' \
        '  --print-only             只打印片段内容，不写任何文件' \
        '  --help                   显示帮助' \
        '路径前缀必须以 / 开头并以 / 结尾，例如 /homework/。' \
        '片段路径与发布目录是写死的：本项目不写共享 nginx 的主配置与 sites-available/sites-enabled/。'
}

fail() {
    printf '错误：%s\n' "$1" >&2
    exit 1
}

arg_error() {
    printf '错误：%s\n' "$1" >&2
    usage >&2
    exit 2
}

require_value() {
    # $1=选项名 $2=剩余参数个数 $3=取值
    if [ "$2" -lt 2 ]; then
        arg_error "$1 缺少取值"
    fi
    if [ -z "$3" ]; then
        arg_error "$1 缺少取值（取值不能为空）"
    fi
    case "$3" in
        --*) arg_error "$1 缺少取值（取值不能以 -- 开头）" ;;
    esac
}

validate_prefix() {
    # $1=选项名 $2=取值；nginx 的 location 前缀必须首尾都是 /。
    case "$2" in
        /*/) ;;
        *) fail "$1 无效：nginx 的 location 前缀必须以 / 开头并以 / 结尾（当前值 ${2}）" ;;
    esac
}

validate_absolute() {
    # $1=选项名 $2=取值
    case "$2" in
        /*) ;;
        *) fail "$1 无效：必须是绝对路径（当前值 ${2}）" ;;
    esac
}

validate_fixed_path() {
    # $1=选项名 $2=取值 $3=唯一允许的取值
    if [ "$2" != "$3" ]; then
        fail "$1 无效：只能是 ${3}；本项目只写自己的 conf.d 片段与发布目录，不得写共享 nginx 的主配置或 sites-available/sites-enabled（当前值 ${2}）"
    fi
}

nginx_available() {
    # $1=nginx 可执行文件：名字走 PATH，含斜杠的按路径判断是否可执行。
    case "$1" in
        */*) [ -x "$1" ] ;;
        *) command -v "$1" >/dev/null 2>&1 ;;
    esac
}

resolve_path() {
    # $1=根前缀 $2=绝对路径
    case "$1" in
        /) printf '%s' "$2" ;;
        */) printf '%s%s' "$1" "${2#/}" ;;
        *) printf '%s/%s' "$1" "${2#/}" ;;
    esac
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --web-prefix) require_value "$1" "$#" "${2-}"; WEB_PREFIX=$2; shift 2 ;;
        --api-prefix) require_value "$1" "$#" "${2-}"; API_PREFIX=$2; shift 2 ;;
        --api-upstream) require_value "$1" "$#" "${2-}"; API_UPSTREAM=$2; shift 2 ;;
        --deploy-dir) require_value "$1" "$#" "${2-}"; DEPLOY_DIR=$2; shift 2 ;;
        --snippet-file) require_value "$1" "$#" "${2-}"; SNIPPET_FILE=$2; shift 2 ;;
        --nginx-bin) require_value "$1" "$#" "${2-}"; NGINX_BIN=$2; shift 2 ;;
        --nginx-main-conf) require_value "$1" "$#" "${2-}"; NGINX_MAIN_CONF=$2; shift 2 ;;
        --root) require_value "$1" "$#" "${2-}"; ROOT_PREFIX=$2; shift 2 ;;
        --no-reload) NO_RELOAD=1; shift ;;
        --print-only) PRINT_ONLY=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) arg_error "无法识别的参数：$1" ;;
    esac
done

# --- 校验：全部先于任何文件写入，失败时不得留下半成品 ---
validate_prefix '--web-prefix' "$WEB_PREFIX"
validate_prefix '--api-prefix' "$API_PREFIX"
validate_absolute '--nginx-main-conf' "$NGINX_MAIN_CONF"
validate_absolute '--root' "$ROOT_PREFIX"
# 写死的两条路径约束：共享 nginx 的主配置与 sites-* 目录不在允许范围内。
validate_fixed_path '--snippet-file' "$SNIPPET_FILE" "$ALLOWED_SNIPPET_FILE"
validate_fixed_path '--deploy-dir' "$DEPLOY_DIR" "$ALLOWED_DEPLOY_DIR"

case "$API_UPSTREAM" in
    127.0.0.1:*)
        PORT=${API_UPSTREAM#127.0.0.1:}
        case "$PORT" in
            ''|*[!0-9]*) fail "--api-upstream 无效：端口必须是 1-65535 的整数（上游 ${API_UPSTREAM}）" ;;
        esac
        # 去掉前导零，避免 test 把 08000 当成八进制。
        while [ "${#PORT}" -gt 1 ] && [ "${PORT#0}" != "$PORT" ]; do
            PORT=${PORT#0}
        done
        if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
            fail "--api-upstream 无效：端口必须是 1-65535 的整数（上游 ${API_UPSTREAM}）"
        fi
        ;;
    *) fail "--api-upstream 无效：上游必须是 127.0.0.1:PORT（当前值 ${API_UPSTREAM}）" ;;
esac
API_UPSTREAM="127.0.0.1:$PORT"

# nginx 可执行文件必须先存在：否则无法校验配置，
# 而校验失败分支会删掉刚写入的片段——那会把“环境缺件”误报成“配置非法”。
# --print-only 不写任何文件，因此不受此项约束。
if [ "$PRINT_ONLY" -eq 0 ] && ! nginx_available "$NGINX_BIN"; then
    fail "找不到 nginx 可执行文件（${NGINX_BIN}）；请用 --nginx-bin 指定 nginx 的绝对路径，或先安装 nginx 后重试；未写入任何文件"
fi

TARGET_SNIPPET=$(resolve_path "$ROOT_PREFIX" "$SNIPPET_FILE")
TARGET_MAIN_CONF=$(resolve_path "$ROOT_PREFIX" "$NGINX_MAIN_CONF")
TARGET_DEPLOY=$(resolve_path "$ROOT_PREFIX" "$DEPLOY_DIR")

# alias 必须以 / 结尾，否则 nginx 拼接路径会出错；
# proxy_pass 不带末尾 /，服务端路由自带 /homework_api 前缀，带上会被剥掉导致 404。
SNIPPET=$(cat <<EOF
# 由 zg-homework-web/scripts/install.sh 生成，请勿手工编辑。
# 同域名多项目共存：本项目独占 ${WEB_PREFIX} 与 ${API_PREFIX} 两个前缀。
# 本片段只含 location 块；server 块与 TLS 证书由运维统一维护。

location ${WEB_PREFIX} {
    alias ${DEPLOY_DIR}/current/;
    index index.html;
    try_files \$uri \$uri/ ${WEB_PREFIX}index.html;
}

location ${API_PREFIX} {
    proxy_pass http://${API_UPSTREAM};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    client_max_body_size 12m;
    proxy_read_timeout 60s;
}
EOF
)

if [ "$PRINT_ONLY" -eq 1 ]; then
    printf '%s\n' "$SNIPPET"
    exit 0
fi

# 主配置由运维维护：片段必须被 include，否则 nginx -t 照样通过但片段不会生效。
if [ ! -f "$TARGET_MAIN_CONF" ]; then
    printf '%s\n' "警告：主配置不存在（${TARGET_MAIN_CONF}），无法确认片段是否被 include" >&2
elif ! grep -q 'include[^;]*conf\.d' "$TARGET_MAIN_CONF"; then
    printf '%s\n' "警告：主配置未 include conf.d 目录，片段不会生效（${TARGET_MAIN_CONF}）" >&2
fi

mkdir -p "$(dirname "$TARGET_SNIPPET")"
mkdir -p "$TARGET_DEPLOY/releases"
chmod 755 "$TARGET_DEPLOY/releases"

# 幂等：片段内容没变就不写文件、不 reload，避免无谓地打扰共享 nginx。
if [ -f "$TARGET_SNIPPET" ] && [ "$(cat "$TARGET_SNIPPET")" = "$SNIPPET" ]; then
    printf '%s\n' "片段未变化，跳过写入与 reload：$TARGET_SNIPPET"
    exit 0
fi

BACKUP=''
TMP_SNIPPET=$TARGET_SNIPPET.tmp

cleanup() {
    # 任何失败路径都不得留下 .bak / .tmp 半成品。
    if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
        rm -f "$BACKUP"
    fi
    if [ -f "$TMP_SNIPPET" ]; then
        rm -f "$TMP_SNIPPET"
    fi
}
trap cleanup EXIT

if [ -f "$TARGET_SNIPPET" ]; then
    BACKUP=$TARGET_SNIPPET.bak
    cp "$TARGET_SNIPPET" "$BACKUP"
fi

# 先写临时文件再原子替换，避免中途失败留下半个片段。
printf '%s\n' "$SNIPPET" > "$TMP_SNIPPET"
chmod 644 "$TMP_SNIPPET"
mv "$TMP_SNIPPET" "$TARGET_SNIPPET"

# 必须先 nginx -t 通过才允许 reload；失败则恢复原片段并以非零码退出。
if ! "$NGINX_BIN" -t -c "$TARGET_MAIN_CONF"; then
    if [ -n "$BACKUP" ] && [ -f "$BACKUP" ]; then
        mv "$BACKUP" "$TARGET_SNIPPET"
        printf '%s\n' "已恢复原片段：$TARGET_SNIPPET" >&2
    else
        rm -f "$TARGET_SNIPPET"
        printf '%s\n' "已删除未通过校验的新片段：$TARGET_SNIPPET" >&2
    fi
    fail "nginx 配置校验失败，未 reload nginx"
fi
rm -f "$BACKUP"

if [ "$NO_RELOAD" -eq 0 ]; then
    if command -v systemctl >/dev/null 2>&1; then
        systemctl reload nginx || fail "nginx reload 失败"
    else
        "$NGINX_BIN" -s reload || fail "nginx reload 失败"
    fi
fi

printf '%s\n' "前端片段已安装：$TARGET_SNIPPET" "发布目录：$TARGET_DEPLOY/releases"
