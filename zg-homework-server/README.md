# zg-homework-server

学校兴趣培养积分系统 —— 服务端模块。

## 独立性

当前聚合检出包含 `zg-homework-server/`、`zg-homework-web/`、`zg-homework-docs/` 三个模块；微信小程序是仓外独立仓库。服务端也可单独检出、启动和打包，运行时不依赖其他模块源码：

- 与客户端**仅通过 HTTP 接口**通信，不引用任何其他模块源码
- 依赖自封闭：`requirements.txt` 为唯一依赖清单
- 配置外置：开发使用 `.env`（从 `.env.example` 复制），systemd 生产配置使用 `/etc/zg-homework-server/env`，代码中不硬编码密钥
- 服务端不可用不影响任何客户端的构建

## 启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 设置 DATABASE_URL、JWT_SECRET，生产环境还需检查 CORS_ORIGINS

# 3. 仅开发联调：确认目标为隔离 MySQL 库后初始化表和联调种子
# 此命令创建已知密码的测试账号，不适用于生产环境
python -m app.seed.initial_data

# 4. 运行
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl -X POST http://127.0.0.1:8000/homework_api/health
# {"code":0,"message":"ok","data":{"status":"ok","env":"dev"}}
```

## Linux systemd 运维

`./scripts/server_run.sh check|status|start|stop|restart` 根据脚本位置使用当前服务端目录，不切换检出。`--help` 显示参数。可设置 `SERVER_UNIT`（默认 `zg-homework-server.service`）、`SERVER_PORT`（默认 `8000`）、`SERVER_PYTHON`（默认本模块 `.venv/bin/python`，须为绝对路径）。路径仅支持 ASCII 字母、数字、`_-. /`（不含空格）。脚本本身需要 Python 3，服务端环境需要 Python 3.12+ 和已安装的 Uvicorn。

归档的 `scripts/production.env.example` 和 `scripts/zg-homework-server.service.example` 提供占位符模板。systemd 生产环境固定使用 `/etc/zg-homework-server/env` 和 `/etc/systemd/system/zg-homework-server.service`。首次安装时确认目标不存在，再由管理员手动安装模板并替换全部 `__...__` 占位符；打包和运行脚本不会安装或覆盖配置。迁移已有部署时先备份并核对原模块 `.env` 和 unit，手动将所需应用设置转换为下述格式；目标文件已存在时不要覆盖，先备份并人工合并。目录和配置文件应由可信管理员管理，仅允许管理员和服务账号读取配置，禁止非授权用户写入；服务账号还需有目录遍历权限。unit 亦须仅允许可信管理员修改。

配置文件严格使用单行 `KEY=value`：键只能是 `app/config.py` 中应用配置字段的大写名称；值不得含单引号、双引号、反斜杠、`$`、控制字符或首尾空白。允许空行及整行 `#` 注释，不支持重复键、行内注释、`export`、引号包裹或多行值。`ZG_HOMEWORK_SYSTEMD_PRODUCTION` 和 `PYTHONDONTWRITEBYTECODE` 是 unit 环境变量，不写入配置文件。

例如模块位于 `/data/apps/zg-homework-server` 时，unit 中 `WorkingDirectory` 设置为该路径，Python 设置为该目录下 `.venv/bin/python`，端口设为 `8000`；生产配置可以使用 `/var/lib/zg-homework/public` 和 `/var/lib/zg-homework/private` 两个互不嵌套的持久目录。MySQL URL 填写专用账号、实际主机和数据库；密码中的 URL 特殊字符需要百分号编码。JWT 应使用独立生成的强随机密钥，不能使用示例值。确保服务账号有目录读写权限，防止路径或符号链接在校验后被改变。

仅供说明的配置格式（其中密码和密钥必须替换，勿将真实凭据提交到仓库）：

```dotenv
ENV=prod
DEBUG=false
DATABASE_URL=mysql+pymysql://homework_user:__DB_PASSWORD__@127.0.0.1:3306/zg_homework?charset=utf8mb4
JWT_SECRET=__JWT_SECRET__
CORS_ORIGINS=https://homework.example.com
UPLOAD_DIR=/var/lib/zg-homework/public
PRIVATE_HOMEWORK_DIR=/var/lib/zg-homework/private
```

以下 unit 示例中的路径和端口须与实际设置完全一致；设置其他端口或 Python 路径时，控制脚本的 `SERVER_PORT` 和 `SERVER_PYTHON` 也须匹配。脚本不安装 unit，也不调用 daemon-reload。

```ini
[Service]
Type=simple
WorkingDirectory=/opt/zg-homework/zg-homework-server
EnvironmentFile=/etc/zg-homework-server/env
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=ZG_HOMEWORK_SYSTEMD_PRODUCTION=1
ExecStart=/opt/zg-homework/zg-homework-server/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
KillMode=control-group
```

unit 使用上述固定的 EnvironmentFile 和两个 Environment 设置，不得有额外 ExecStart 命令、前后置/停止钩子、额外 EnvironmentFile 或 Environment、PassEnvironment、UnsetEnvironment、PAMName、RootDirectory 或 RootImage；systemd 管理器环境不得包含 `PYTHON*` 或 `UVICORN_*`。生产配置须显式设置 `ENV=prod`（或 `production`）、`DEBUG=false`、MySQL `DATABASE_URL` 和非默认 `JWT_SECRET`。运维还应核对凭据、服务用户权限、systemd 管理器环境及数据库连通性。生产环境必须显式设置 `UPLOAD_DIR` 和 `PRIVATE_HOMEWORK_DIR` 为检出之外的绝对路径，并使用持久存储。按仓库发布约定应从已验证的 `main` 检出部署。

修改 unit 后由管理员执行 `systemctl daemon-reload`，再重启服务；仅修改环境文件也须重启服务才能生效，无需因此执行 daemon-reload。重启前先核对配置和目标 unit。

注意：此配置尚需在隔离的 Linux/systemd 环境实机验证后再用于生产。systemd 管理器环境也不得包含应用配置变量、`LD_*` 或生产标志，以避免配置来源冲突。

`check` 检查运行时、配置、unit、端口及运行状态；`status` 检查 unit、端口及健康状态，不检查运行时。均不控制服务。已运行的 `start` 是幂等操作，不重新加载源码；更新代码用 `restart`。`stop` 对已停止服务幂等；仅控制经验证的指定 unit，不按端口或名称杀进程。运行中要求主进程的命令、工作目录、cgroup、环境和监听端口符合约定，无法核实时拒绝操作。执行者需有 systemd 控制权限及读取 `/proc` 主进程信息的权限。unit 和代码须由可信管理员管理，执行时不得并发修改配置或另行控制 unit；检查和 systemd 控制之间不是原子操作。

启动前检查 `app/` 中是否存在 `.pyc`/`.pyo` 或符号链接，有则拒绝启动，请运维确认后自行处理，不自动删除。不要让其他工具在检查后向源码写入字节码。应用启动不建表、不执行种子或迁移；生产业务使用前须由运维确认数据库目标、备份并单独初始化或迁移表结构。`POST /homework_api/health` 仅检查应用存活，不验证数据库或表结构。失败返回非零并提示 `journalctl -u UNIT -n 100 --no-pager`；启动失败不会自动停止服务或回滚源码。回退时由运维恢复已验证的源码版本及配置，再运行 `restart`；涉及数据库变更须另行按备份和迁移流程处理。

## 源码部署包

```bash
./scripts/server_package.sh  # 默认输出到 ../zg-homework-tests/tar/
./scripts/server_package.sh -o /已有目录/zg-homework-server.tar.gz
```

打包需要 Python 3。输出路径须位于模块目录之外，且目标文件不能已存在。归档读取脚本所在模块当前工作树，包括未提交源码；不会拉取代码或切换分支。按仓库约定，生产打包应在经验证的 `main` 检出执行，打包期间不要修改源码。

归档包含 `app/` 下的 Python 源码、依赖清单、配置示例、Docker 配置、README 及运行和打包脚本；不包含测试、虚拟环境、缓存、真实 `.env`、公开上传和私有附件。分发前仍需人工检查源码与示例配置是否包含敏感信息。解压到新的目录后安装 Python 依赖，并单独准备生产环境文件 `/etc/zg-homework-server/env`、持久化存储和 systemd 配置。

**注意：** 打包仅收集文件，不验证或修复运行脚本。当前运行脚本仍存在生产安全问题，也尚未完成 Linux/systemd 实机验证；尤其要确保私有附件目录和公开上传目录互不嵌套，完成安全修复和隔离验证后才可生产部署。

## Docker 打包

```bash
docker build -t zg-homework-server:1.0.0 .
docker run -d -p 8000:8000 --env-file .env \
  -e PRIVATE_HOMEWORK_DIR=/app/private_homework \
  -v zg-homework-private-homework:/app/private_homework \
  -v zg-homework-public-uploads:/app/app/uploads \
  zg-homework-server:1.0.0
```

作业私有附件由 `PRIVATE_HOMEWORK_DIR` 配置，默认是服务端目录下的
`private_homework`（镜像中为 `/app/private_homework`），不通过静态目录公开。
生产环境应使用绝对路径并挂载持久化卷；上例显式指定目录，防止 `.env` 中的
其他配置使挂载失效。自定义目录应位于仓库及 Docker 构建上下文之外，且不能
位于 `UPLOAD_DIR` 内；确保服务进程有读写权限，限制其他用户访问。多实例需
共享相同附件存储，并与数据库一起备份、恢复。已有默认目录中的文件在修改路径前
须迁移至新目录。公开上传目录也需独立持久化，不能与私有目录重叠。

提交数据库时若发生异常，提交结果可能不确定，附件会保留以避免删除已被引用的
文件，可能因此产生孤儿文件。回收时应先备份，暂停所有上传及数据库写入，并等待
在途请求结束、确认数据库事务结果；对照当前数据库中所有 `private:` 附件引用，
仅删除确认不再被引用且超过安全等待期的文件。不要仅按文件年龄自动删除。

## 目录结构

```
app/
├── main.py          应用入口（不自动建表 + 统一异常处理）
├── config.py        配置（读 .env）
├── db/session.py    引擎与会话（MySQL + 连接池）
├── db/repo.py       仓储层（SQLAlchemy 实现）
├── models/
│   ├── constants.py    枚举常量（角色、状态等）
│   └── entities.py     SQLAlchemy 模型（14 张表）
├── schemas/         Pydantic 出入参
├── routers/         路由：auth / admin / classes / homework /
│                    point_rules_admin / checkin / points /
│                    articles / games
├── services/        point_rule_service（60s 缓存）/ point_service /
│                    sudoku（生成算法）/ idiom（题库与会话）
├── utils/           security(jwt/bcrypt) / deps(权限依赖) / response
│                    reset_password(重置密码) / purge_test_data(清理测试数据)
├── seed/            建表与种子脚本（python -m app.seed.initial_data）
└── uploads/         上传文件（git 忽略内容）

tests/               pytest 测试
```

## 数据库：MySQL

数据落在 `DATABASE_URL` 指定的 MySQL 库，默认库名 `zg_homework`，字符集 **utf8mb4**。先确保数据库已存在，并核对实际连接；环境变量 `DATABASE_URL` 优先于 `.env`。开发种子含已知密码的联调账号，不适用于生产环境。

```bash
# 1. 建表 + 种子（幂等，可重复执行）
python -m app.seed.initial_data

# 2. 危险：删除当前目标库的 ORM 表及其全部数据后重建，无二次确认
# 仅在确认是可丢弃的隔离库、备份并明确需要重置时执行：
# python -m app.seed.initial_data --reset
# 不会删除数据库本身，也不是常规初始化步骤；原有表结构升级需单独迁移。
```

> 连接配置在 `.env` 的 `DATABASE_URL`。
> **应用启动不自动建表或执行种子。** 生产环境须事先由运维确认目标库、备份并单独准备结构与安全的初始数据；开发种子含已知密码账号，不适用于生产。现有数据库的结构变更须另行迁移。

### 种子写入的基础数据

| 类型          | 内容                                             |
|-------------|------------------------------------------------|
| admin       | 用户名 `admin`，密码取 `ADMIN_INIT_PASSWORD`；未设置则随机生成并打印日志，首登强制改密 |
| 积分规则       | PRD 4.2 的 10 条默认规则                          |
| 联调账号      | `teacher01` / `student01` / `student02` / `parent01`，密码统一 `test123456` |
| 老师邀请码     | `TEACH2024`（未使用状态）                          |

### 联调账号

| 用户名         | 角色     | 密码          |
|-------------|--------|-------------|
| `teacher01` | teacher | `test123456` |
| `student01` | student | `test123456` |
| `student02` | student | `test123456` |
| `parent01`  | parent  | `test123456` |

> 首次执行时 admin 密码随机生成，**仅打印一次**；
> 也可先在 `.env` 设 `ADMIN_INIT_PASSWORD` 固定密码。
>
> **密码忘了怎么办**：用重置命令改回一个已知密码
>
> ```bash
> python -m app.utils.reset_password admin --password 'admin123456'
> ```
>
> 省略 `--password` 则随机生成并打印。重置后账号会解除禁用状态，
> 并置 `must_change_password`，下次登录强制改密。
>
> ⚠️ 不要把随机种子密码写进文档 —— 首次改密后它就失效了，
> 按文档登录会一直返回 400。

## 测试

```bash
# 明确指向专用隔离 MySQL 数据库，替换连接信息后执行
DATABASE_URL='mysql+pymysql://user:password@127.0.0.1:3306/zg_homework_test?charset=utf8mb4' pytest
```

覆盖：
- **认证**：登录/注册、四角色登录、JWT 载荷与 7 天有效期、bcrypt 落库、
  跨会话持久化、中文 utf8mb4
- **admin**：邀请码全生命周期（生成/筛选/撤销/一码一用）、admin 账号保护、
  禁用后 JWT 立即失效与恢复、重置密码强制改密、用户列表筛选搜索、
  审计日志、全局统计
- **积分规则**：列表/详情/单条更新/批量更新、rule_key 不可改、JSON 校验、
  审计日志、缓存即时生效
- **积分发放**：规则驱动、日次数上限、规则禁用不发放、游戏跨规则合计上限、
  家长扣分余额校验、余额不为负、明细可追溯
- **班级**：创建/加入/查询/成员列表/移除；6 位邀请码；一个学生只属一个班级；
  跨班操作 403
- **作业**：布置/列表/今日/详情/完成情况/删除；开始不覆盖首次时间；
  提交 multipart；迟交标记；用时<1 分钟标记异常；按时/迟交分别发放积分；
  有人提交后禁止删除
- **签到**：每日一次不重复发放、连续天数计算（含断签重置）、第 7 天连签奖励
- **排行榜**：日榜按当日流水、总榜按余额；同分按达成时间；排除 admin；
  my_rank 在前 50 之外也可见；家长无榜权限（PRD 8）
- **积分**：明细分页与类型筛选、概览（今日/累计获得/累计消费/余额）
- **家长**：绑定/多孩子/解绑、孩子明细与概览、预设扣分事项（看手机5/看电视5/
  买玩具20/买零食10）、余额不足拦截、流水记负数且 operator 为家长；
  跨家长访问孩子 403
- **阅读**：teacher/admin 发布、学生仅见 published、心跳 30s±10s 防挂机
  （异常不计分）、每分钟 +1、读完 +5 单篇一次、老师仅管自己的文章与记录
- **游戏**：数独三档难度内置生成（唯一解校验）、提交答案服务端复核防伪造、
  成语接龙 60 秒闯关答对 +1/题、题目与选项分离、未取题不可作答防重放、
  游戏合计每日 20 分封顶（跨数独与成语）
- **题库**：admin 批量导入（同批去重、skip/overwrite 模式）、编辑、启用开关、
  单条与批量删除；干扰项不足时服务端补齐
- **通用**：统一响应格式、无入参接口接受空 Body

> **测试必须使用专用隔离数据库。** 测试连接真实 MySQL，会提交数据并调用包括删除在内的业务接口，可能留下数据或修改共享状态；不能依赖用户名 `test_` 前缀或假设只增不删。不要在开发库或生产库运行。`tests/` 不入库，干净检出可能缺失；未收集到测试不代表测试通过。
>
> 清理工具有破坏性，先确认 `DATABASE_URL` 实际目标并检查 dry-run，确认范围后才考虑执行：
>
> ```bash
> python -m app.utils.purge_test_data --dry-run   # 先看统计
> python -m app.utils.purge_test_data             # 交互确认后清理
> python -m app.utils.purge_test_data --by-keep-list  # 只留种子数据，连旧命名残留一起清
> ```
>
> 不要把 `--reset` 当作常规清理：它无二次确认地删掉目标库 ORM 表及数据，具体限制见上方数据库章节。

## 接口契约

业务接口使用 `/homework_api` 前缀，通常为 POST + JSON Body，文件上传使用 multipart；上传文件通过 GET 提供。统一响应 `{code, message, data}`。
完整清单见 PRD 第 7 节（`zg-homework-docs` 仓库的 `sys_doc/PRD.md`）——
这是与其他模块的唯一契约来源。

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

## 开发进度

- [x] P0 骨架：配置、health 检查、Dockerfile、目录结构
- [x] P1 JWT 认证 + 注册登录
- [x] P1b 接入 MySQL：14 张表 + 种子数据
- [x] P1.5 admin 基础：邀请码管理、用户管理、全局统计
- [x] P1.6 积分规则管理 + 积分发放服务
- [x] P2 班级与作业
- [x] P3 签到与排行榜
- [x] P4 家长绑定与扣分
- [x] P5 课后阅读（252 测试通过）
- [ ] P6 游戏（含成语题库导入）
## 验收脚本

验收脚本位于聚合检出的 `zg-homework-docs`；以下从聚合仓库根目录运行。业务验收需要服务端运行在 `127.0.0.1:8000`，并提供已有 admin 的密码：

```bash
# 业务验收（PRD 第 12 节，对真实接口逐条验证）
ACCEPTANCE_ADMIN_PASSWORD='<已有 admin 密码>' .venv/bin/python zg-homework-docs/scripts/acceptance_check.py

# 模块独立性检查（PRD 第 12 节「模块独立性」）
python zg-homework-docs/scripts/independence_check.py
```

> 业务验收调用真实接口并留下持久数据，建议使用隔离环境；脚本不会重置 admin，且跳过修改共享积分规则和删除数据的验收项。独立性检查是静态检查，仅覆盖 server 和 web，无需启动服务或数据库。

## 联调前端

聚合检出中三个模块目录同级；也可使用分别检出的模块。以下在聚合目录下执行：

```bash
# 终端 1：启动服务端
cd zg-homework-server && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：启动 Web 端（Vite 代理 /homework_api → 127.0.0.1:8000）
cd zg-homework-web && npm run dev
```

浏览器打开 http://localhost:5173

> Vite 代理保留 `/homework_api` 前缀转发，服务端路由也带此（前缀不可剥除）；
> `VITE_PROXY_TARGET` 可配置服务端地址，默认 `http://127.0.0.1:8000`。
