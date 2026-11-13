#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
exec python3 "$ROOT/zg-homework-docs/scripts/deploy_tool.py" package "$ROOT" "$@"
