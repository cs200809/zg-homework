# zg-homework

> 注意：根目录 Makefile、运维、打包、部署及验收脚本已移除。下文涉及这些脚本的命令为历史说明，不能执行；服务端和 Web 请分别按各自依赖清单运行。

学习兴趣培养积分系统：服务端、Web 端与文档在同一仓库的三个模块目录中维护。

| 目录 | 内容 | 技术栈 |
|---|---|---|
| `zg-homework-server/` | 服务端 | Python / FastAPI / SQLAlchemy / MySQL 8 |
| `zg-homework-web/` | Web 端 | React / Vite / Ant Design |
| `zg-homework-docs/` | 契约、配置与验收 | Markdown / Python |

**分支与发布约定**：在 `feature/dev_deploy` 分支开发和测试，测试通过后合并到 `main` 主分支；打包和部署均使用 `main` 分支代码。

模块保留各自依赖清单、构建与发布边界。微信小程序是仓外独立仓库，位于 `~/WeChatProjects/HomeworkPoints`，见 [小程序规划](zg-homework-docs/sys_doc/小程序.md)。需求与接口契约以 [PRD](zg-homework-docs/sys_doc/PRD.md) 为准。

## 快速开始

以下命令从仓库根目录执行，需要 Python 3.12、Node.js >= 20、MySQL 8 及 mysql 客户端。先配置并确认目标数据库，再初始化，最后启动服务：

```bash
# 创建脚本默认使用的根目录虚拟环境，并用同一解释器安装依赖
python3.12 -m venv .venv
.venv/bin/python -m pip install -r zg-homework-server/requirements.txt
npm --prefix zg-homework-web install

# 首次配置；若 .env 已存在，跳过复制以免覆盖
cp zg-homework-server/.env.example zg-homework-server/.env
# 编辑 zg-homework-server/.env：设置 DATABASE_URL、JWT_SECRET
# 确认 MySQL 连接、库名及 SQL 来源均为预期的开发环境后执行
make db-init

make help
make dev
```

`make db-init` 会写入真实数据库；默认不删除数据库。脚本读取 `.env` 的 `DATABASE_URL`，`MYSQL_*` 环境变量可覆盖其中的连接信息；服务端则优先读取环境变量 `DATABASE_URL`。执行前确认两者指向同一目标，且未意外指定 `REPOS_DIR`。脚本只读取环境变量 `ADMIN_INIT_PASSWORD`，不读取 `.env` 中的该项；未通过环境变量设置时会生成随机密码。新建 admin 时请妥善保存显示的密码并在首次登录后修改。服务启动也会对目标库执行 `create_all`，但不会自动写入种子。

如使用其他虚拟环境，请通过 `VENV_PY` 指定其 Python，并用该解释器安装依赖。Web 默认地址为 <http://localhost:5173>；健康检查使用 `POST /homework_api/health`，例如 `curl -X POST http://127.0.0.1:8000/homework_api/health`。

| 命令 | 用途 |
|---|---|
| `make dev` / `make server` / `make web` | 启动两个服务或其中之一 |
| `make status` / `make logs` | 查看状态 / 跟随日志 |
| `make stop` | 仅停止身份核验通过的记录进程；未核验进程需手动处理 |
| `make db-init` | 初始化真实数据库；`ARGS=--drop` 会删库重建 |
| `make test` | 运行服务端 pytest |
| `make build` | Web 类型检查与构建 |
| `make check` | 静态模块边界检查，无需服务端或数据库 |
| `make acceptance` | 运行真实接口业务验收 |

`make stop` 根据 PID、进程启动时间及命令行核验记录的进程，仅向核验通过的进程发送停止信号；旧格式或无法核验的记录会被跳过，不按端口清理，也不自动终止子进程。残留进程或端口占用需要先确认身份再手动处理。启动时间在部分系统上只有秒级精度，身份核验与发送信号也不是原子操作，不能完全排除 PID 重用竞态。`make status` 只检查端口占用，不能证明占用者是本项目进程。

**测试和业务验收均会写真实数据库。** pytest 会提交数据并可能删除数据；测试目录不入库，缺失或未收集到测试时不算成功。请明确配置专用隔离 MySQL 后运行。业务验收要求服务端运行在 `127.0.0.1:8000`，并设置 `ACCEPTANCE_ADMIN_PASSWORD`；它会创建持久数据，不能当作只读检查。当前脚本跳过修改共享积分规则和删除数据的验收项。

## 数据库初始化

`scripts/init.sh` 默认使用本仓库的 `zg-homework-docs/sql/init.sql` 和 `zg-homework-server/.env`；可用 `REPOS_DIR` 显式指定其他代码目录，无效时直接报错。初始化会写真实数据库，执行前确认数据库与 SQL 来源；`--drop` 删库且需二次确认。

SQL 由服务端 `python -m app.seed.export_ddl` 从 ORM 生成。脚本用 `ADMIN_INIT_PASSWORD` 或随机密码替换 admin 哈希占位符；不会覆盖已有正常密码。直接导入未替换的 SQL 不能正常初始化 admin。开发联调种子可用 `python -m app.seed.initial_data`，同样会操作数据库。

## 文档

- [需求、接口及验收标准](zg-homework-docs/sys_doc/PRD.md)
- [环境配置](zg-homework-docs/sys_doc/config.md)
- [小程序规划与分期](zg-homework-docs/sys_doc/小程序.md)：一期学生与家长，老师与 admin 排在二期。
