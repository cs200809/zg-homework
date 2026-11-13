# CLAUDE.md

> 仓库根目录没有顶层构建入口，也没有顶层运维/初始化脚本和文档验收脚本——历史文档里提到的这些入口都已删除，属不可执行的历史说明。但**打包与部署脚本是存在的**，在各模块的 `scripts/` 下（清单见「部署脚本清单」），参数一律以各自的 `--help` 输出为准。

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库形态

本项目采用单一仓库，包含服务端、Web 和文档三个模块目录。微信小程序端是仓外独立仓库，位于 `~/WeChatProjects/HomeworkPoints`，不在本检出中。各模块保留独立依赖与构建边界：

| 目录 | 内容 | 技术栈 |
|------|------|--------|
| `zg-homework-server/` | 服务端 | Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 |
| `zg-homework-web/` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 / Zustand 5 |
| `zg-homework-docs/` | **契约与文档**（PRD、config、建表 SQL、设计与计划文档） | Markdown / SQL |

**需求与 API 契约的权威来源是 `zg-homework-docs/sys_doc/PRD.md`**（v2.3）。它同时承担了 PRD、API 契约、数据库建表 SQL、权限矩阵、验收清单五重角色。改接口前先读它；改完后要同步 `zg-homework-web/src/api/types.ts`（这份是 PRD 的手工副本，无自动生成）。
**分支与发布约定**：在 `feature/dev_deploy` 分支开发和测试，测试通过后合并到 `main` 主分支；打包和部署均使用 `main` 分支代码。

### 三个必须知道的结构性事实

1. **微信小程序端是仓外独立仓库**，位于 `~/WeChatProjects/HomeworkPoints`，**不在本检出内**。它是原生小程序（WXML/WXSS/JS），规划与验收见 `zg-homework-docs/sys_doc/小程序.md`。服务端与 Web 端无需为它做任何改动。

2. **可执行脚本都在各模块的 `scripts/` 下，没有仓库根级入口**。服务端在 `zg-homework-server/scripts/`（`install.sh`、`server_run.sh`、`server_package.sh`、`init_check.sh`），前端在 `zg-homework-web/scripts/`（`install.sh`、`web_deploy.sh`、`web_package.sh`、`web_run.sh`）。每个脚本都用自己的 `--help` 输出真实参数，不要照抄任何文档里的命令行。

3. **PRD 里的建表 SQL 是 SQLite 方言**，而服务端实际跑 MySQL 8。库表结构以 `zg-homework-server/app/models/entities.py`（15 张表）为准，PRD 第 4.1 节仅作参考。

## 常用命令

没有仓库根级的统一入口，命令分模块执行。

### 服务端

```bash
cd zg-homework-server
pip install -r requirements.txt
cp .env.example .env            # 按需改 DATABASE_URL / JWT_SECRET

python -m app.seed.initial_data        # 建表 + 种子（幂等）
python -m app.seed.initial_data --reset # 删表重建（危险）
python -m app.seed.apply_comments      # 给已有表补字段中文 COMMENT

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`.env` 路径基于 `app/config.py` 向上两级，不依赖 CWD；环境变量优先级高于 `.env`。

**建表 SQL 参考文件**：`zg-homework-docs/sql/init.sql` 由 `python -m app.seed.export_ddl` **从 ORM 生成**（改了 `app/models/entities.py` 要重新生成），是 MySQL 8 方言的建表 + 规则种子脚本。它的 admin 种子带 `__ADMIN_BCRYPT_HASH__` 占位符（未替换时那条 INSERT 会被自身的 `WHERE` 条件跳过）。**不要拿它当初始化入口**——日常初始化一律用 `python -m app.seed.initial_data`：幂等，不覆盖已存在的 admin 密码，依赖项目自带的 PyMySQL（不需要 mysql 客户端）。

`initial_data` 会一并写入联调数据（一个班级、4 个测试账号 `teacher01`/`student01`/`student02`/`parent01`——统一密码 `test123456`、家长绑定、老师邀请码 `TEACH2024`、10 条成语题库样例）。**在空的生产库上跑，它同样会创建这批测试账号**——`app/seed/initial_data.py` 的 `seed_dev_accounts()` 只在库里已有第二个用户时才跳过。生产初始化后请立刻禁用或删除这些账号。

**健康检查是 POST，不是 GET**：`curl -X POST http://127.0.0.1:8000/homework_api/health` 返回统一响应，`data` 含 `status` 和当前 `env`。浏览器直接打开会 405（CORS `allow_methods` 只放行 `POST, OPTIONS`）。

测试（**需要可连的 MySQL**，不 mock、不用 sqlite）：

```bash
pytest                          # 全部
pytest tests/test_auth.py       # 单文件
pytest tests/test_auth.py::test_login_success   # 单用例
pytest -k "login" -x -vv
```

测试使用配置的真实 MySQL，会提交数据并调用包括删除在内的业务接口，可能留下数据；**使用专用隔离数据库，不要假定测试只插入或更新**。例如 `DATABASE_URL=mysql+pymysql://.../zg_homework_other pytest`。`tests/` 被 gitignore，干净检出可能没有测试文件。清理工具有破坏性，先查看 `python -m app.utils.purge_test_data --dry-run` 的结果并确认目标数据库。

### Web 端

```bash
cd zg-homework-web
npm install        # Node >=20
npm run dev        # vite --mode development，端口 5173
npm run build      # = tsc -b && vite build --mode production（含类型检查）
npm run build:dev
npm run preview
```

**`npm run lint` 当前必然失败**——脚本存在但仓库里没有任何 ESLint 配置文件（无 `.eslintrc*` / `eslint.config.*`）。要修需补 ESLint 8 的 eslintrc 格式配置。Prettier 完全没有，格式化靠手写。

### 顶层运维脚本

不存在。仓库根目录没有 `scripts/` 目录，也没有任何一键启动/停止脚本。开发期的服务端与 Web 端各自手动启动（见上面的「服务端」「Web 端」两节）。

### 部署脚本清单

| 脚本 | 用途 | 可否重跑 | 写入范围 |
|---|---|---|---|
| `zg-homework-server/scripts/install.sh` | 渲染 systemd 单元、生成生产配置、建数据目录、建/复用 venv | 是（已有 venv 复用、已有 env 保留、已有数据目录不重建） | `/etc/systemd/system/zg-homework-server.service`、`/etc/zg-homework-server/env`、`/var/lib/zg-homework/`、检出目录内的 `.venv` |
| `zg-homework-server/scripts/server_run.sh` | 单元控制器：`check`/`status`/`start`/`stop`/`restart` | 是（`start` 幂等：已运行且健康则不动） | 不写文件（只调用 `systemctl`） |
| `zg-homework-server/scripts/server_package.sh` | 服务端源码归档（白名单：`app/` + `requirements.txt` + `scripts/` 等固定文件） | 是（输出文件名必须不存在） | 只写指定的 `.tar.gz` 输出文件，默认 `zg-homework-tests/tar/` |
| `zg-homework-server/scripts/init_check.sh` | 创建 `.venv` 并安装依赖 | 否（**拒绝覆盖**已有 `.venv`，重建须先自行删除） | 检出目录内的 `.venv` |
| `zg-homework-web/scripts/install.sh` | 生成共享 nginx 片段、建 `releases/`、校验并 reload | 是（片段内容未变则跳过写入与 reload） | `/etc/nginx/conf.d/zg-homework.conf`、`/var/lib/zg-homework-web/releases/` |
| `zg-homework-web/scripts/web_deploy.sh` | 发布前端：解包静态包或本机构建 → 版本目录 → `nginx -t` → 原子切 `current` → reload，失败自动回滚 | 是（每次发布新增一个版本目录，不覆盖旧的） | `/var/lib/zg-homework-web/**`（**不写 `/etc/nginx/` 下任何文件**） |
| `zg-homework-web/scripts/web_package.sh` | 构建并打包静态部署包（`--source` 打包源码） | 是（输出文件名必须不存在） | 只写指定的 `.tar.gz` 输出文件，默认 `zg-homework-tests/tar/` |
| `zg-homework-web/scripts/web_run.sh` | **独占 nginx 形态**的前端控制器（本方案不使用；使用者必须把 `WEB_DEPLOY_DIR` 指到别处） | 是（`start` 幂等；`restart` 会构建新版本） | 构建产物写入 `WEB_DEPLOY_DIR` 指向的目录；unit 与专用 nginx 配置只校验不写 |

### 云服务器部署（裸机 systemd + 共享 nginx，多项目共存）

生产机多项目共存，**同一域名 + 路径前缀**区分：本项目占 `/homework/`（前端）与 `/homework_api/`（API）。共享 nginx 的主配置、`server` 块与 TLS 证书由**运维**统一维护，本项目只写自己的片段 `/etc/nginx/conf.d/zg-homework.conf`。

打包（开发机或 CI，产物不含任何凭据）：

```bash
cd zg-homework-server && sh scripts/server_package.sh   # → zg-homework-tests/tar/zg-homework-server-<ts>.tar.gz
cd zg-homework-web    && sh scripts/web_package.sh       # → zg-homework-tests/tar/zg-homework-web-static-<ts>.tar.gz
```

两种前端产物的分工：

- **静态包**（`web_package.sh` 默认形态）：先 `tsc --noEmit` 再 `vite build`，已注入 `VITE_API_BASE_URL=/homework_api`、以 `--base /homework/` 构建。顶层目录名固定为 `zg-homework-web-static/`，**生产机用它发布，不需要 Node**。
- **源码包**（`web_package.sh --source`）：顶层目录名是 `zg-homework-web/`，**不能直接发布**——`web_deploy.sh --package` 会以「静态包的顶层目录必须是 `zg-homework-web-static/`」拒绝。只用于把源码传到服务器后自行构建（走 `web_deploy.sh --build`）。

目标机上执行（需 root）：

```bash
# 服务端：解压 → 安装 → 校验
sudo mkdir -p /data/apps/zg-homework-server
sudo tar -xzf zg-homework-server-<ts>.tar.gz -C /data/apps/zg-homework-server --strip-components=1
cd /data/apps/zg-homework-server
sudo sh scripts/install.sh \
     --server-dir /data/apps/zg-homework-server \
     --api-port 8000 \
     --database-url 'mysql+pymysql://user:pass@127.0.0.1:3306/zg_homework?charset=utf8mb4'
sudo sh scripts/server_run.sh check

# Web 端：生成 nginx 片段 → 发布静态包
cd /data/apps/zg-homework-web
sudo sh scripts/install.sh --api-upstream 127.0.0.1:8000
sudo sh scripts/web_deploy.sh --package /tmp/zg-homework-web-static-<ts>.tar.gz
```

Web 端的两个脚本要能在目标机上执行，**目标机上得有 `zg-homework-web/scripts/`**（把源码包 `web_package.sh --source` 传过去，或在目标机上放一份检出）。静态包本身只含 `index.html` 与 `assets/`。

数据库初始化（`install.sh` **不**做这一步，必须手工执行）：

```bash
sudo -u www-data bash -c '
  set -a; . /etc/zg-homework-server/env; set +a
  cd /data/apps/zg-homework-server && ./.venv/bin/python -m app.seed.initial_data
'
```

`initial_data` 幂等，重复执行不重复插入，**不覆盖已存在的 admin 密码**；`ADMIN_INIT_PASSWORD` 为空时随机生成密码并只打印一次。env 文件的取值不含引号、反斜杠、`$` 与首尾空白（`server_run.sh` 的硬约束），因此可以被 shell 正常 `source`。

**无迁移框架**：`create_all()` 只建缺失的表，不给已有表加列。涉及表结构的升级需按 `app/seed/migrate_*.py` 单独执行迁移（`migrate_v21`、`migrate_homework_review`、`migrate_article_soft_delete`），迁移前备份数据库。

部署架构：**同域反代**。前端 `VITE_API_BASE_URL=/homework_api`，nginx 把 `/homework_api/` 转发给服务端
（服务端路由本身就带 `/homework_api` 前缀，`proxy_pass` **不带**末尾 `/`，不剥除前缀）。
因此**不需要 CORS，服务端 8000 端口只监听 `127.0.0.1`，不对公网开放**。
完整方案见 `zg-homework-docs/sys_doc/生产部署打包方案.md`。

关键约束：

- **systemd 固定单 worker**（`ExecStart` 里 `--workers 1`）。成语接龙会话在进程内存
  （`app/routers/games.py` 的 `SessionStore`），多 worker 会丢会话。`server_run.sh` 逐字校验 `ExecStart`，不是 1 直接拒绝控制该单元。
- **上传数据必须在代码目录之外**（默认 `/var/lib/zg-homework/`），否则升级覆盖代码时会丢文件。规则比「检出目录之外」更严：`UPLOAD_DIR` 与 `PRIVATE_HOMEWORK_DIR` 不得等于、也不得位于检出目录的**上级目录**之下，且两者互不重叠。
- **`proxy_pass` 不带末尾 `/`**（剥了前缀后端会收到 `/login` 而不是 `/homework_api/login` → 404）；**`alias` 必须带末尾 `/`**（`alias /var/lib/zg-homework-web/current/;`）。
- **任何脚本都不得写** `/etc/nginx/nginx.conf`、`sites-available/`、`sites-enabled/`；只写自己的 `conf.d` 片段，且 reload 前必须 `nginx -t` 通过（`nginx -t` 不通过就不切换、不 reload）。
- **生产配置由 `scripts/install.sh` 生成**（`/etc/zg-homework-server/env`，`0640 root:www-data`）：值中不得含 `'"\$` 或未替换的 `__…__` 占位符，`server_run.sh` 会直接拒绝。重复执行时保留已有 `JWT_SECRET`（避免轮换密钥导致已签发 token 失效）与运维手填的键；需要整体重建时才加 `--force-env`（会重新生成 `JWT_SECRET`，存量 token 立即失效）。
- **端口改动要三处同步**：`install.sh --api-port`、`server_run.sh` 的 `SERVER_PORT` 环境变量、前端 `install.sh --api-upstream`。

### 验收

契约测试在 **`zg-homework-tests/`**（该目录被 gitignore，是本地联调资产，不入库；干净检出可能没有这些文件）：

```bash
cd /Users/zg/PycharmProjects/zg-homework
python3 -m unittest discover -s zg-homework-tests -p 'test_*.py' -v
```

覆盖打包脚本白名单、两端 `install.sh` 的产物、`web_deploy.sh` 的发布/回滚语义、`server_run.sh` 与 `web_run.sh` 的控制器契约、生产单元与配置契约。这些是**沙箱测试**，不触碰真实 systemd/nginx/数据库；临时产物落在根 `docs/` 下。

`zg-homework-docs/scripts/` 下的业务验收脚本与模块独立性检查脚本**不在本仓库中**——PRD 第 12 节的接口级验收需要人工按 PRD 逐条执行。

## 服务端架构

```
routers → services → db/repo.py → models/entities.py
routers → schemas/（仅 auth、admin 有独立文件，其余 Pydantic 模型内联在 router 里）
```

目录是 `app/routers/`、`app/config.py`、`app/db/`、`app/utils/`——**没有 `app/core/` 或 `app/api/`**。

### 全 POST + 统一响应

业务接口通常使用 `POST` + JSON Body，参数不进 URL；作业提交和文章文件上传使用 multipart 表单。`/uploads` 静态文件通过 GET 提供，挂载本身没有鉴权依赖。业务响应为 `{code, message, data}`，分页数据在 `data` 里嵌 `{list, total, page, size}`。

`app/utils/response.py` 提供 `ok()` / `fail()`；`app/main.py` 注册三个全局异常处理器。**router 里抛 `HTTPException` 时 `detail` 必须是 `{"code": ..., "message": ...}` 字典**，否则 handler 会退化成 `fail(status_code, str(detail))`。各 router 文件顶部自带一份 `_bad_request/_forbidden/_not_found` 私有 helper 来保证这个形状。

### 鉴权：无中间件，全靠依赖

`app/utils/deps.py` 是唯一鉴权入口，四个依赖：

- `get_current_user` — 解析 `Bearer` token，**每次请求都查库**（所以后台禁用用户后已签发的 JWT 立即生效，不能加缓存）
- `get_verified_user` — 额外拦截 `must_change_password` 的 admin
- `require_roles(*roles)` / `require_admin` — 角色工厂

JWT payload 只有 `user_id/role/exp`，**role 在 payload 里但从不用于判断**——实际角色一律回库读 `user.role`。

角色控制分三级：

1. **路由级**：admin 组用 `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` 整组锁死。
2. **函数级**：teacher/student/parent 路由用 `get_verified_user` 后在函数体第一行判断角色（每个 router 各自定义 `_require_teacher` 等私有 helper）。
3. **数据级**：防越权的关键，每个 router 各写一份，如 `_own_class_or_403`（校验 `klass.teacher_id != user.id`）、`_own_child`（校验 `parent_students` 关系）。admin 账号不可被任何 admin 操作（`_protect_admin`）。

注册只开放 student/teacher/parent（`REGISTERABLE_ROLES`）；teacher 注册必须带有效邀请码，**一码一用**。

### 数据层

`app/db/repo.py` 是共享数据访问层，但并非唯一入口：router 和 service 也直接使用 SQLAlchemy session。事务通常由 router 提交，Repo 通常负责 add/flush 而不 commit；没有 Unit of Work。积分操作依赖学生行锁及锁定读来控制并发，修改时保留这些语义。

`app/db/session.py`：`pool_pre_ping=True` + `pool_recycle=3600`（应对 MySQL 8h 空闲断连），`autoflush=False`。

MySQL 适配约定：无真 BOOLEAN，用 `Boolean`（映射 TINYINT(1)）；JSON 字段一律用 `Text` 存 JSON 字符串，以对齐 PRD 建表 SQL。

### 无迁移框架

没有 Alembic。`create_all()` **只建缺失的表，不给已有表增加列或索引**；`python -m app.seed.apply_comments` 只补已有字段的注释，不能替代迁移。存量库升级参见 `app/seed/migrate_v21.py`、`migrate_article_soft_delete.py` 和 `migrate_homework_review.py`。作业批改迁移前先备份、停止业务写入并确认连接，先运行 `python -m app.seed.migrate_homework_review --check`，再按脚本说明执行；留意 MySQL DDL 隐式提交和已有空档位表的处理。

### 积分规则的两个语义陷阱

`point_rules.daily_limit` 是「**每天最多 N 次**」，不是积分上限。`checkin_daily = {points: 5, daily_limit: 1}` 意为「每天签到 1 次，每次给 5 分」。命中次数上限时 `award()` 直接返回 0，**不做部分发放**。唯一例外是游戏（`award_game()`），那里 `daily_limit` 当作**跨规则的当日积分总和上限**，超出时按剩余额度部分发放。

`point_logs` 表没有 `rule_key` 列，按 `type` 区分流水。家长扣分 `consume()` 走负数流水 + `operator_id`，**不查 `point_rules`**。作业批改使用独立的 `homework_review_rules` 档位和 `review` 流水；重批改按目标变化调整积分，余额不足时扣至零、未扣足部分永久豁免，实际累计变动可能不同于目标积分。

### 其它值得知道的实现

- **积分规则缓存**：`app/services/point_rule_service.py` 进程内单例 + `threading.Lock` + 60s TTL，admin 改规则后调 `invalidate(rule_key)` 精确失效。
- **数独是算法生成**，不预置题库：回溯生成完整解 → 按难度挖空（easy 36 / medium 48 / hard 54 空）→ 校验唯一解。学生提交由服务端复核。
- **阅读心跳防挂机**：客户端声明 `seconds`，服务端校验 `seconds <= 30 + 10`，超限则本次不计分但仍记录。
- **成语游戏会话在内存**（`app/routers/games.py` 的 `SessionStore` + `threading.Lock`），60 秒限时，**不落库**，多进程部署会丢会话。
- **bcrypt 直用原生库，不用 passlib**（passlib 1.7.4 读 bcrypt 4.1+ 已移除的 `__about__.__version__`，每次加载 backend 都打印告警）。两种实现哈希格式一致，存量可校验。`passlib[bcrypt]` 只作为测试依赖。

## Web 端架构

```
src/
├── api/         client.ts（axios 实例 + post 封装）+ auth/classes/student/parent/adminIdioms + types.ts
├── components/  AdminLayout.tsx、ReviewModal.tsx 等公共组件
├── router/      index.tsx（路由 + 角色守卫）
├── store/       auth.ts（Zustand 单一 store）
└── pages/       common/ student/ teacher/ admin/ parent/
```

- **代理**：`vite.config.ts` 把 `/homework_api` 代理到 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）——服务端路由本身就带 `/homework_api` 前缀，**不得剥除**（剥了会 404）。`loadEnv` 第三参为空串，故 `VITE_PROXY_TARGET` 可被运行时环境变量覆盖。
- **API 层**：`api/client.ts` 里 `post<T>()` 封装统一响应，`code !== 0` 时抛带 `code` 属性的 Error。**没有 401/403 全局拦截**——运行期 token 过期不会自动登出，只在应用启动的 `store/auth.ts` `init()` 里做一次 `/auth/me` 探测并清 localStorage。
- **角色分流两段式**：路由守卫 `Protected roles={[...]}`（`router/index.tsx`）+ 菜单白名单 `MENUS: Record<Role, NavItem[]>`（`components/AdminLayout.tsx`）。admin 首登未改密会被强制跳到 `/change-password`。
- **状态**：Zustand 单一 store，手动读写 localStorage（key `token` / `user`），无 persist 中间件。
- **路由无懒加载**：`router/index.tsx` 静态 import 全部页面，无 `lazy`/`Suspense`。
- **页面数据获取**：`useCallback` + `useEffect` + `useState` 三件套，`Promise.all` 并发拉取，错误走 `message.error`。全站无 react-query。
- **手机号校验**：`src/utils/phone.ts` 是校验规则的唯一来源，与服务端 `app/schemas/auth.py` 的 `PHONE_PATTERN`、小程序 `utils/validate.js` 三处必须一致。**注册严格**（非手机号一律拒绝），**登录仅校验纯数字输入**——服务端 `admin` 账号的用户名是 `admin`（非手机号），若登录也强制手机号格式，管理员将无法登录。改规则时三处一起改。
- **已知职责错位**：`api/parent.ts` 里混放了 admin 的全部接口（invite/user/rule/article/stats），文件命名与内容不符。

**部署**：`Dockerfile` 两阶段（node:20-alpine 构建 → nginx:alpine），`nginx.conf` 配了 `location /homework_api/` 反代到 `http://server:8000`、`client_max_body_size 12m`（作业文件上传）、SPA 回退 `try_files ... /index.html`。`.env.production` 的 baseURL 已是 `/homework_api`，与反代语义一致。仍**没有 docker-compose.yml**，且反代指向的 `server:8000` 无 compose 支撑——Docker 路径需自备 compose；裸机部署走「云服务器部署」一节（服务端 `scripts/server_package.sh`、前端 `scripts/web_package.sh`）。

## 已知缺陷（已验证，动手前先看这里）

以下都是**已实测确认**的现存问题，不是猜测：

1. **服务端限流未实现**。`app/config.py` 定义了 `register_rate_limit` / `action_rate_limit`，`.env.example` 也配了，但整个 `app/` 里除定义处无第二处引用。

2. **`npm run lint` 必然失败** —— 仓库里没有 ESLint 配置文件（无 `.eslintrc*` / `eslint.config.*`），脚本是空壳。

3. **Web 无 401 全局拦截** —— 运行期 token 过期不会自动登出，只在应用启动的 `init()` 里做一次 `/auth/me` 探测。

4. **Web 路由无懒加载** —— 页面全静态 import，首屏包含全部页面。

5. **`api/parent.ts` 里混放了 admin 的全部接口**（invite/user/rule/article/stats），文件职责与命名不符。

6. **nginx 反代目标无 compose 支撑** —— `.env.production` 的 `VITE_API_BASE_URL=/homework_api` 与 nginx 的 `location /homework_api/` 语义一致（**已修复**）。裸机部署见「云服务器部署」一节。仍存留的问题是 **nginx 反代指向的 `server:8000` 无 compose 支撑**（Docker 路径仍需自备 compose）。仓库里那个 `nginx.conf` 属于 Docker 独占形态，**不是**生产共享 nginx 的片段——生产片段由 `zg-homework-web/scripts/install.sh` 生成，内容只有 `location` 块。

7. **`zg-homework-docs/sys_doc/PRD.md` 2.2.1 与实现仍有出入**：PRD 第 4.1 节的建表 SQL 是 SQLite 方言，权威定义在 `zg-homework-server/app/models/entities.py`。

8. **PRD 第 12 节的接口级验收脚本不在仓库内**：`zg-homework-docs/scripts/` 下的验收与独立性检查脚本已随旧文档移除，仓库只有 `zg-homework-tests/` 里的脚本契约测试（不入库）。接口级验收目前只能人工按 PRD 逐条执行。

9. **`web_run.sh` 与 `web_deploy.sh` 的默认发布目录相同**（都是 `/var/lib/zg-homework-web`），冲突是默认可达的。本方案只用 `web_deploy.sh`；若要用 `web_run.sh`，必须把 `WEB_DEPLOY_DIR` 指到别处。

## 历史修复记录

以下是此前的修复记录。实际状态应以正在修改的检出为准：

- **服务端 Dockerfile HEALTHCHECK**：改为显式 POST 探针（原先用 GET 探 POST-only 的 `/health`，永远 405）。
- **`.env.example` 的无效 `HOST` / `PORT`**：已删除，改为注明 host/port 由 uvicorn 命令行决定。
- **PRD 与实现不一致**：PRD 2.1 的 SQLite 已改为 MySQL 8；第 7 节接口清单已补 `POST /games/idiom/question`。

## Git 约定

- 主分支 `main`；服务端、Web 和文档在同一仓库中维护。历史拆分分支与其他检出可能仍存在，不应未经确认删除。
- **服务端测试不入库**：`zg-homework-server/tests/` 被 gitignore，本地测试属于联调资产，干净检出不一定存在。测试连接真实数据库且可能执行删除，使用专用隔离库。
- **契约测试与临时产物不入库**：`zg-homework-tests/`（打包/安装/发布脚本的契约测试）与根 `docs/`（临时产物与临时脚本）都被 gitignore，属本地联调资产。
- `.dev-logs/`、`/dist/`、`.venv/`、各 `.env` 均不入库；打包产物默认落在 `zg-homework-tests/tar/`，同样不入库。
- 根 `.claude/settings.local.json` 只有 `permissions.allow` 一个节点，无 deny/ask/env/hooks/mcpServers 配置。
