#!/bin/sh
# zg-tsp 数据库初始化脚本
#
# 一条命令完成：建库 → 建 14 张表 → 写积分规则种子 → 创建 admin 账户。
#
# 用法：
#   ./scripts/init.sh            # 初始化（幂等，可重复执行）
#   ./scripts/init.sh --drop     # 先删库再重建（危险，需二次确认）
#   ./scripts/init.sh --help
#
# 环境变量：
#   REPOS_DIR            五个仓库所在目录（默认自动探测，同 dev.sh）
#   ADMIN_INIT_PASSWORD  admin 初始密码（未设则随机生成并打印一次）
#   MYSQL_HOST/MYSQL_PORT/MYSQL_USER/MYSQL_PASSWORD/MYSQL_DATABASE
#                        覆盖 .env 中 DATABASE_URL 的解析结果
#
# 说明：
#   · 建表 SQL 由 `python -m app.seed.export_ddl` 从 ORM 生成，
#     落在 zg-tsp-docs/sql/init.sql，本脚本不重新生成（避免误改交付物）。
#   · 本脚本保持 POSIX sh 兼容：可用 sh / bash / zsh / dash 执行，
#     不使用数组、[[ ]]、进程替换等 bash 专有语法。

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"

# --- 颜色 ---
if [ -t 1 ]; then
  ESC=$(printf '\033')
  R="${ESC}[0;31m"; G="${ESC}[0;32m"; Y="${ESC}[0;33m"; B="${ESC}[0;36m"; N="${ESC}[0m"
else
  R=""; G=""; Y=""; B=""; N=""
fi

info() { echo "${B}==>${N} $*"; }
ok()   { echo "  ${G}✓${N} $*"; }
warn() { echo "  ${Y}!${N} $*"; }
err()  { echo "  ${R}✗${N} $*" >&2; }
die()  { err "$*"; exit 1; }

# --- 参数 ---
DROP_DB=0
for arg in "$@"; do
  case "$arg" in
    --drop) DROP_DB=1 ;;
    --help|-h)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "未知参数：$arg（用 --help 查看用法）" ;;
  esac
done

# --- 定位仓库目录 ---
# 与 dev.sh 的探测顺序保持一致：环境变量 → ../zg-tsp-repos → 本快照 → ~/zg-tsp-repos
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

INIT_SQL="${REPOS_DIR}/zg-tsp-docs/sql/init.sql"
SERVER_DIR="${REPOS_DIR}/zg-tsp-server"

# --- 读取 .env 中的 DATABASE_URL ---
# .env 路径基于 app/config.py 向上两级，不依赖 CWD
ENV_FILE="${SERVER_DIR}/.env"
DB_HOST="${MYSQL_HOST:-}"
DB_PORT="${MYSQL_PORT:-}"
DB_USER="${MYSQL_USER:-}"
DB_PASSWORD="${MYSQL_PASSWORD:-}"
DB_NAME="${MYSQL_DATABASE:-}"

read_env_value() {
  # 从 .env 中取某个 key 的值（取等号后内容，去掉首尾空白与引号）
  [ -f "$1" ] || return 0
  local key="$2" line
  line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$1" | tail -n 1) || return 0
  [ -n "$line" ] || return 0
  line=${line#*=}
  # 去掉行尾注释与引号
  line=$(printf '%s' "$line" | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")
  printf '%s' "$line"
}

if [ -z "${DB_HOST}${DB_PORT}${DB_USER}${DB_NAME}" ] || [ -f "${ENV_FILE}" ]; then
  DATABASE_URL=$(read_env_value "${ENV_FILE}" "DATABASE_URL")
  if [ -n "${DATABASE_URL}" ]; then
    # 形如 mysql+pymysql://user:password@host:port/dbname?charset=utf8mb4
    url_no_scheme=${DATABASE_URL#*://}
    url_no_query=${url_no_scheme%%\?*}
    credentials=${url_no_query%@*}
    hostpart=${url_no_query##*@}
    db_part=${hostpart#*/}
    host_part=${hostpart%%/*}
    env_user=${credentials%%:*}
    env_password=${credentials#*:}
    if [ "${env_password}" = "${credentials}" ]; then env_password=""; fi
    env_host=${host_part%%:*}
    env_port=${host_part##*:}
    if [ "${env_port}" = "${host_part}" ]; then env_port="3306"; fi

    # .env 提供默认值，MYSQL_* 环境变量优先
    [ -n "${DB_USER}" ] || DB_USER="${env_user}"
    [ -n "${DB_PASSWORD}" ] || DB_PASSWORD="${env_password}"
    [ -n "${DB_HOST}" ] || DB_HOST="${env_host}"
    [ -n "${DB_PORT}" ] || DB_PORT="${env_port}"
    [ -n "${DB_NAME}" ] || DB_NAME="${db_part}"
  fi
fi

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_NAME="${DB_NAME:-zg_tsp}"

[ -n "${DB_NAME}" ] || die "无法确定数据库名：请检查 ${ENV_FILE} 中的 DATABASE_URL"

info "数据库：${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
info "SQL 文件：${INIT_SQL}"

# --- 检查 mysql 客户端 ---
command -v mysql >/dev/null 2>&1 || die "找不到 mysql 客户端，请先安装（brew install mysql / apt install mysql-client）"

# 用 MYSQL_PWD 传密码，避免密码出现在进程命令行里
mysql_run() {
  MYSQL_PWD="${DB_PASSWORD}" mysql \
    --default-character-set=utf8mb4 \
    -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" "$@"
}

# --- 删除并重建 ---
if [ "${DROP_DB}" -eq 1 ]; then
  warn "即将删除数据库 ${DB_NAME}，该库内所有数据将丢失！"
  printf "确认删除请输入大写 YES："
  read -r answer
  if [ "${answer}" != "YES" ]; then
    die "已取消，未做任何改动"
  fi
  info "删除数据库 ${DB_NAME}"
  mysql_run -e "DROP DATABASE IF EXISTS \`${DB_NAME}\`;" || die "删除失败"
fi

info "创建数据库 ${DB_NAME}（如已存在则跳过）"
mysql_run -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\`
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;" || die "创建数据库失败"

# --- 生成 admin 密码与 bcrypt 哈希 ---
server_python() {
  if [ -n "${VENV_PY:-}" ] && [ -x "${VENV_PY}" ]; then
    echo "$VENV_PY"
  elif [ -x "${ROOT}/.venv/bin/python" ]; then
    echo "${ROOT}/.venv/bin/python"
  elif [ -x "${SERVER_DIR}/.venv/bin/python" ]; then
    echo "${SERVER_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    echo "python3"
  else
    return 1
  fi
}

ADMIN_PASSWORD="${ADMIN_INIT_PASSWORD:-}"
if [ -z "${ADMIN_PASSWORD}" ]; then
  # 随机生成（16 字符，字母数字），仅本次显示
  if command -v openssl >/dev/null 2>&1; then
    ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-16)
  else
    ADMIN_PASSWORD=$(awk 'BEGIN{srand();s="";for(i=0;i<16;i++){s=s substr("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789",int(rand()*56)+1,1)}print s}')
  fi
  PASSWORD_IS_RANDOM=1
else
  PASSWORD_IS_RANDOM=0
fi
[ -n "${ADMIN_PASSWORD}" ] || die "生成 admin 密码失败"

# 优先用服务端的 hash_password（bcrypt rounds=12，与登录校验完全一致）；
# 没有 Python 环境时回退 htpasswd（产出 $2y$，服务端 bcrypt 同样能校验）。
ADMIN_HASH=""
PY=""
PY=$(server_python) || PY=""
if [ -n "${PY}" ]; then
  ADMIN_HASH=$(cd "${SERVER_DIR}" && "${PY}" -c '
import sys
sys.path.insert(0, ".")
try:
    from app.utils.security import hash_password
except Exception:
    import bcrypt
    def hash_password(p):
        return bcrypt.hashpw(p.encode(), bcrypt.gensalt(rounds=12)).decode()
print(hash_password(sys.argv[1]))
' "${ADMIN_PASSWORD}" 2>/dev/null) || ADMIN_HASH=""
fi

if [ -z "${ADMIN_HASH}" ]; then
  if command -v htpasswd >/dev/null 2>&1; then
    warn "服务端 Python 不可用，回退到 htpasswd 生成 bcrypt 哈希"
    ADMIN_HASH=$(htpasswd -bnBC 12 "" "${ADMIN_PASSWORD}" | tr -d ':\n')
  else
    die "无法生成 admin 密码哈希：既没有可用的 Python + bcrypt，也没有 htpasswd。
请安装其一，或手动执行：
  mysql --default-character-set=utf8mb4 <库名> < ${INIT_SQL}
并自行把 ${ADMIN_HASH_PLACEHOLDER:-__ADMIN_BCRYPT_HASH__} 替换成 bcrypt 哈希。"
  fi
fi

[ -n "${ADMIN_HASH}" ] || die "生成 admin 密码哈希失败"

# --- 替换占位符并导入 ---
info "导入建表 SQL（14 张表 + 积分规则 + admin）"

# 用 sed 在管道里替换占位符，不改动交付的 init.sql 本身。
# bcrypt 哈希含 `.` `/` `$` 等字符：sed 替换串中只有 `\` `&` 和分隔符是特殊的，
# 故选用 `|` 作分隔符，并转义 `\ & |` 三者。
ESC_HASH=$(printf '%s' "${ADMIN_HASH}" | sed -e 's/[\\&|]/\\&/g')

# macOS 的 mktemp 要求模板以 X 结尾，Linux 允许后缀，两边兼容的写法如下：
TMP_SQL="$(mktemp "${TMPDIR:-/tmp}/zg_tsp_init.XXXXXX")"
trap 'rm -f "${TMP_SQL}"' EXIT INT TERM
sed "s|__ADMIN_BCRYPT_HASH__|${ESC_HASH}|g" "${INIT_SQL}" > "${TMP_SQL}"

mysql_run "${DB_NAME}" < "${TMP_SQL}" || die "导入 SQL 失败"

# --- 校验 ---
TABLE_COUNT=$(mysql_run -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${DB_NAME}';" 2>/dev/null || echo 0)
FK_COUNT=$(mysql_run -N -e "SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema='${DB_NAME}' AND constraint_type='FOREIGN KEY';" 2>/dev/null || echo 0)
RULE_COUNT=$(mysql_run -N -e "SELECT COUNT(*) FROM \`${DB_NAME}\`.point_rules;" 2>/dev/null || echo 0)
ADMIN_EXISTS=$(mysql_run -N -e "SELECT COUNT(*) FROM \`${DB_NAME}\`.users WHERE username='admin';" 2>/dev/null || echo 0)
ADMIN_MUST_CHANGE=$(mysql_run -N -e "SELECT must_change_password FROM \`${DB_NAME}\`.users WHERE username='admin';" 2>/dev/null || echo "")

[ "${TABLE_COUNT}" = "14" ] || die "校验失败：期望 14 张表，实际 ${TABLE_COUNT} 张"
[ "${FK_COUNT}" = "20" ] || warn "外键数量为 ${FK_COUNT}（期望 20），请检查"

if [ "${ADMIN_EXISTS}" = "1" ]; then
  ok "表 ${TABLE_COUNT} 张 / 外键 ${FK_COUNT} 个 / 积分规则 ${RULE_COUNT} 条 / admin 已创建"
else
  die "校验失败：admin 账户未创建"
fi

# --- 输出 admin 凭据 ---
echo ""
ok "初始化完成"
echo ""
echo "  管理员账号： admin"
if [ "${PASSWORD_IS_RANDOM}" -eq 1 ]; then
  echo "  初始密码：   ${ADMIN_PASSWORD}   ${Y}(随机生成，仅本次显示)${N}"
else
  echo "  初始密码：   （取自 ADMIN_INIT_PASSWORD）"
fi
if [ "${ADMIN_MUST_CHANGE}" = "1" ]; then
  echo "  ${Y}首次登录后必须修改密码${N}（must_change_password=1）"
else
  echo "  ${Y}注意：admin 已存在，密码未被改动${N}"
fi
echo ""
echo "  启动服务端： cd ${SERVER_DIR} && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
