# 单仓模块常用入口。测试与业务验收会写真实数据库。
SHELL := /bin/sh
ROOT := $(CURDIR)
PY ?= $(if $(wildcard $(ROOT)/.venv/bin/python),$(ROOT)/.venv/bin/python,python3)
.DEFAULT_GOAL := help

.PHONY: help dev server web stop status logs db-init test build check acceptance
help: ## 显示帮助
	@printf '%s\n' 'zg-tsp 单仓模块入口' '测试和业务验收会写真实数据库，请使用专用隔离库。'
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' "$(ROOT)/Makefile"

dev: ## 启动服务端与 Web
	@"$(ROOT)/scripts/dev.sh" start
server: ## 启动服务端
	@"$(ROOT)/scripts/dev.sh" server
web: ## 启动 Web
	@"$(ROOT)/scripts/dev.sh" web
stop: ## 仅停止身份核验通过的记录进程；未核验进程需手动处理
	@"$(ROOT)/scripts/dev.sh" stop
status: ## 查看状态
	@"$(ROOT)/scripts/dev.sh" status
logs: ## 跟随日志
	@"$(ROOT)/scripts/dev.sh" logs
db-init: ## 初始化真实数据库（ARGS=--drop 会删库）
	@"$(ROOT)/scripts/init.sh" $(ARGS)
test: ## pytest，写真实数据库；无测试时失败
	@test -d "$(ROOT)/zg-tsp-server/tests" || { printf '%s\n' '缺少服务端 tests/，无法运行测试。' >&2; exit 1; }
	@cd "$(ROOT)/zg-tsp-server" && "$(PY)" -m pytest tests
build: ## Web 类型检查与构建
	@cd "$(ROOT)/zg-tsp-web" && npm run build
check: ## 仅运行静态模块边界检查
	@"$(PY)" "$(ROOT)/zg-tsp-docs/scripts/independence_check.py"
acceptance: ## 业务验收，写真实数据库；需运行服务与管理员密码
	@"$(PY)" "$(ROOT)/zg-tsp-docs/scripts/acceptance_check.py"
