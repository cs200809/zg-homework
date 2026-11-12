#!/bin/sh
# Prepare a new deployment's virtual environment without modifying an existing one.
set -eu

if [ "$#" -gt 0 ]; then
    if [ "$#" -eq 1 ] && [ "$1" = '--help' ]; then
        printf '%s\n' '用法：sh scripts/init_check.sh' 'INIT_PYTHON：用于创建虚拟环境的 Python（默认 python3，要求 3.12+）'
        exit 0
    fi
    printf '%s\n' '错误：不支持的参数；请使用 --help 查看用法' >&2
    exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
PYTHON=${INIT_PYTHON:-python3}
VENV=$ROOT/.venv
REQUIREMENTS=$ROOT/requirements.txt

if [ ! -f "$REQUIREMENTS" ]; then
    printf '%s\n' '错误：缺少 requirements.txt' >&2
    exit 1
fi
if ! command -v "$PYTHON" >/dev/null 2>&1 || ! "$PYTHON" -I -B -c 'import sys; assert sys.version_info >= (3, 12)' >/dev/null 2>&1; then
    printf '%s\n' '错误：INIT_PYTHON 必须指定可用的 Python 3.12 或更高版本' >&2
    exit 1
fi
if ! mkdir "$VENV" 2>/dev/null; then
    printf '%s\n' '错误：无法创建 .venv；目标可能已存在，请检查，脚本不会覆盖' >&2
    exit 1
fi

if ! "$PYTHON" -m venv "$VENV" ||
   ! "$VENV/bin/python" -m pip install -r "$REQUIREMENTS" ||
   ! "$VENV/bin/python" -I -B -c 'import sys, uvicorn; assert sys.version_info >= (3, 12)' ||
   ! "$VENV/bin/python" -m pip check; then
    printf '%s\n' '错误：环境初始化失败；.venv 可能不完整，未自动删除，请确认未被服务使用后人工处理' >&2
    exit 1
fi

printf '%s\n' "虚拟环境及依赖检查完成：$VENV" '请核对生产配置和 systemd 单元后运行 sh scripts/server_run.sh check'
