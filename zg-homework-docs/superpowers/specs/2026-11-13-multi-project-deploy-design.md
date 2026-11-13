# 多项目共存的生产部署方案 —— 设计文档

- 日期：2026-11-13
- 分支：`feature/dev_deploy`
- 状态：已确认，待实施
- 触发文档：`zg-homework-docs/sys_doc/生产部署打包方案.md`（现为旧版单人部署草稿）

---

## 1. 背景与问题

### 1.1 旧版部署方案与项目实际已脱节

`zg-homework-docs/sys_doc/生产部署打包方案.md` 描述的是「单项目独占服务器」的裸机部署，与本仓库现有的可执行契约存在系统性冲突：

| 项 | 旧文档 | 项目实际（权威） |
|---|---|---|
| 后端端口 | 8001 | 8000（`server_run.sh` `SERVER_PORT`、`production.env.example`） |
| 进程模型 | gunicorn `-w 2` 多 worker | 必须 `--workers 1`：成语接龙会话在进程内存（`app/routers/games.py` 的 `SessionStore`），多 worker 丢会话 |
| nginx | 共享 `sites-available` + `server_name` + `location` 前缀 | `web_run.sh` 要求**独占** systemd nginx unit + 专用配置 `/etc/zg-homework-web/nginx.conf`，且 `verify_unit()` 逐字节比对配置 |
| 数据目录 | 未规定（隐含在代码目录内） | 上传数据必须外置于检出目录之外（`server_run.sh` 强校验 `UPLOAD_DIR`/`PRIVATE_HOMEWORK_DIR` 不在检出目录内且互不重叠） |
| 数据库初始化 | 缺失 | `python -m app.seed.initial_data`（幂等）/ `zg-homework-docs/sql/init.sql` |
| 日常更新流程 | `-- TODO` 未写 | 需补完 |

### 1.2 真实约束：生产机多项目共存

生产服务器上**多个项目共存**，且按**同一域名 + 路径前缀**区分：

```
https://xxx.com/other/…       → 其它项目
https://xxx.com/homework/      → 本项目前端
https://xxx.com/homework_api/  → 本项目后端
```

由此产生两个硬约束：

1. 旧文档的「独占 nginx server 块 + 独立域名」写法不适用——同域名下多个项目只能靠路径前缀区分。
2. 现有 `web_run.sh` 的独占 nginx 契约（`verify_unit()` 要求 `ExecStart` 必须是 `nginx -c <专用配置>`，且配置内容必须逐字节等于内部生成的 `expected_config()`）**在结构上排斥共享 nginx**。

### 1.3 目标

产出一套在多项目共存下可落地、且与本仓库现有脚本契约自洽的生产部署方案：

- 修订《生产部署打包方案.md》为多项目共存版权威文档；
- 新增服务端 / 前端各自的 `install.sh`，消除 systemd unit 模板的手工渲染；
- 新增 `web_deploy.sh`，在不改动 `web_run.sh` 及其契约测试的前提下，让前端在共享 nginx 下完成构建、发布、切换与回滚；
- 同步 `CLAUDE.md` 的过时描述。

---

## 2. 总体拓扑与共存边界

### 2.1 拓扑

```
生产机 :80/:443
└── 共享 nginx（主配置 / server 块 / TLS 证书 = 运维统一维护，本项目不触碰）
    ├── /other/…        → 其它项目
    ├── /homework/      → 本项目前端静态
    │     alias /var/lib/zg-homework-web/current/
    └── /homework_api/  → 本项目后端
          proxy_pass http://127.0.0.1:8000
          └── systemd: zg-homework-server.service
               └── /data/apps/zg-homework-server  (代码检出，WorkingDirectory)
```

### 2.2 归属清单

| 资源 | 归属 | 说明 |
|---|---|---|
| 路径前缀 `/homework/`、`/homework_api/` | 本项目 | 多项目共存下的唯一身份标识 |
| 端口 8000（`127.0.0.1`） | 本项目 | 多项目共存时需查端口分配表，避免撞车 |
| `/data/apps/zg-homework-server/` | 本项目 | 服务端代码检出；systemd `WorkingDirectory` 必须等于它 |
| `/var/lib/zg-homework/` | 本项目 | 上传数据（`uploads/`、`private_homework/`） |
| `/var/lib/zg-homework-web/` | 本项目 | 前端产物（`releases/`、`current` 符号链接） |
| `/etc/zg-homework-server/env` | 本项目 | 唯一环境文件 |
| `/etc/nginx/conf.d/zg-homework.conf` | 本项目 | 共享 nginx 中的**本项目片段** |
| `/etc/nginx/nginx.conf`、`sites-available/`、`sites-enabled/` | **运维** | 本项目脚本一律不写 |
| server 块、TLS 证书 | **运维** | 同域名共用一张证书，本项目不申请、不续期 |

### 2.3 写入纪律（硬边界）

1. 本项目任何脚本**不得**写 `/etc/nginx/nginx.conf`、`/etc/nginx/sites-available/`、`/etc/nginx/sites-enabled/`。
2. 本项目只允许写自己的 `/etc/nginx/conf.d/zg-homework.conf`。
3. 片段内**只允许 `location` 块**，不得出现 `server` / `events` / `http` 块——否则会与主配置的 server 块冲突或重复监听。
4. reload 共享 nginx 是本项目对其它项目的**唯一**跨项目影响面；因此必须 `nginx -t` 通过后才 reload。`nginx -s reload` 是平滑的（老 worker 处理完在途连接后退出），不打断其它项目的请求。

---

## 3. 目录与数据规划

| 路径 | 内容 | 生命周期 |
|---|---|---|
| `/data/apps/zg-homework-server/` | 服务端代码检出 | 升级时覆盖；`.venv` 在其内部 |
| `/data/apps/zg-homework-server/.venv/` | Python 虚拟环境 | `init_check.sh` 创建，不覆盖已有 |
| `/var/lib/zg-homework/uploads/` | 公开上传（`/uploads` 静态挂载） | 持久，**不得**在代码目录内 |
| `/var/lib/zg-homework/private_homework/` | 私有作业附件 | 持久，**不得**在代码目录内 |
| `/var/lib/zg-homework-web/releases/<版本>/` | 前端构建产物 | 每次发布新增一个目录 |
| `/var/lib/zg-homework-web/current` | 指向当前版本的符号链接 | 原子切换，切换失败自动回滚 |
| `/etc/zg-homework-server/env` | 服务端环境变量 | 由 `install.sh` 生成，`640 root:www-data` |
| `/etc/systemd/system/zg-homework-server.service` | systemd 单元 | 由 `install.sh` 渲染 |
| `/etc/nginx/conf.d/zg-homework.conf` | 共享 nginx 片段 | 由 web `install.sh` 生成 |

`UPLOAD_DIR` 与 `PRIVATE_HOMEWORK_DIR` 必须**在检出目录之外**且**互不重叠**——这是 `server_run.sh` 的既有强校验，本方案沿用 `/var/lib/zg-homework/` 下的两个子目录天然满足。

---

## 4. 脚本设计

### 4.1 总览

| 脚本 | 状态 | 职责 | 写入范围 |
|---|---|---|---|
| `zg-homework-server/scripts/install.sh` | 新增 | 渲染 systemd unit + 生成 env + 建数据目录 + 建 venv | `/etc/systemd/system/zg-homework-server.service`、`/etc/zg-homework-server/env`、`/var/lib/zg-homework/**` |
| `zg-homework-web/scripts/install.sh` | 新增 | 生成 nginx 片段 + 建发布目录 | `/etc/nginx/conf.d/zg-homework.conf`、`/var/lib/zg-homework-web/**` |
| `zg-homework-web/scripts/web_deploy.sh` | 新增 | 构建前端 → 发布 `releases/<版本>` → 原子切 `current` → `nginx -t` → reload | `/var/lib/zg-homework-web/**` |
| `zg-homework-server/scripts/server_run.sh` | 不变 | systemd 单元的 check/status/start/stop/restart | 不写文件 |
| `zg-homework-server/scripts/server_package.sh` | 仅改白名单 | 服务端源码归档；白名单增加 `scripts/install.sh` | — |
| `zg-homework-server/scripts/init_check.sh` | 不变 | 创建 `.venv` | — |
| `zg-homework-web/scripts/web_package.sh` | 不变 | 前端静态包 / 源码包 | — |
| `zg-homework-web/scripts/web_run.sh` | 不变 | 独占 nginx 模式（保留，本方案不使用） | — |

**既有契约测试 `zg-homework-tests/test_run_scripts.py`、`test_production_contract.py`、`test_package_scripts.py` 零改动。**

### 4.2 服务端 `install.sh`

**用法**

```bash
sudo zg-homework-server/scripts/install.sh \
  --server-dir /data/apps/zg-homework-server \
  --api-port 8000 \
  --service-user www-data --service-group www-data \
  --database-url 'mysql+pymysql://user:pass@127.0.0.1:3306/zg_homework?charset=utf8mb4' \
  --cors-origins 'https://xxx.com' \
  --data-dir /var/lib/zg-homework
```

**参数**

| 参数 | 默认 | 说明 |
|---|---|---|
| `--server-dir` | `/data/apps/zg-homework-server` | 服务端代码检出目录；systemd `WorkingDirectory` 必须等于它 |
| `--api-port` | `8000` | 后端监听端口（仅 `127.0.0.1`） |
| `--service-user` / `--service-group` | `www-data` | systemd 运行身份 |
| `--database-url` | 无（必填） | `mysql+pymysql://…?charset=utf8mb4` |
| `--jwt-secret` | 无 | 不给则用 `openssl rand -hex 32` 生成并打印一次 |
| `--cors-origins` | 无（可选） | 同域反代下通常留空；给了则注入 `CORS_ORIGINS` |
| `--data-dir` | `/var/lib/zg-homework` | 上传数据根目录 |
| `--skip-venv` | 关 | 跳过 venv 创建（已有 venv 时用） |
| `--no-start` | 关 | 装完不 `systemctl enable --now` |
| `--force-env` | 关 | 覆盖已存在的 `/etc/zg-homework-server/env`（默认保留） |

**行为**

1. 校验：`--server-dir` 必须是已存在真实目录（含 `app/main.py`）；`--api-port` 为合法端口；`--database-url` 以 `mysql+pymysql://` 开头；`--data-dir` 必须在 `--server-dir` 之外。
2. 渲染 systemd 单元：读 `scripts/zg-homework-server.service.example`，替换占位符 `__SERVER_MODULE_DIR__`、`__SERVER_PYTHON__`（= `<server-dir>/.venv/bin/python`）、`__SERVICE_USER__`、`__SERVICE_GROUP__`、`__SERVER_PORT__`，写入 `/etc/systemd/system/zg-homework-server.service`（`0644`）。
   - 渲染后的 `ExecStart` 必须**逐字**等于 `<python> -m uvicorn app.main:app --host 127.0.0.1 --port <port> --workers 1`，否则 `server_run.sh` 会拒绝控制。
   - `EnvironmentFile` 必须是 `/etc/zg-homework-server/env`（唯一环境文件），`Type=simple`，`KillMode=control-group`，`Environment=` 仅 `PYTHONDONTWRITEBYTECODE=1` 与 `ZG_HOMEWORK_SYSTEMD_PRODUCTION=1`。
3. 生成 `/etc/zg-homework-server/env`（`0640 root:<service-group>`）：
   - 以 `scripts/production.env.example` 为骨架，替换 `DATABASE_URL`、`JWT_SECRET`、`UPLOAD_DIR`、`PRIVATE_HOMEWORK_DIR`、`CORS_ORIGINS`、`ENV=prod`、`DEBUG=false`。
   - **值不得包含 `'"\$` 与控制字符**——`server_run.sh` 的配置校验会直接拒绝；占位符未替换时同样拒绝。
   - 保留 `production.env.example` 中 `ENV/DEBUG/DB_ECHO/JWT_ALGORITHM/JWT_EXPIRE_DAYS/ADMIN_INIT_PASSWORD/MAX_UPLOAD_MB/ALLOWED_EXTENSIONS/ARTICLE_*` 等其余键。
   - **已存在 env 时的语义**：默认**不覆盖**整个文件，只更新本次显式指定的键；`JWT_SECRET` 若已存在且未显式传 `--jwt-secret`，保留原值（避免每次部署轮换密钥导致已签发 token 全部失效）；传 `--force-env` 才整体重写。
4. 建数据目录 `<data-dir>/uploads`、`<data-dir>/private_homework`，属主 `<service-user>:<service-group>`，`0750`。
5. 建 venv：复用 `scripts/init_check.sh`（它拒绝覆盖已存在的 `.venv`）。
6. `systemctl daemon-reload`；除非 `--no-start`，`systemctl enable --now zg-homework-server`。
7. 打印部署摘要（端口、路径、unit 名）与后续步骤（数据库初始化见 §6）。

**幂等**：重复执行不报错、不覆盖已存在的 `env` 中的 `JWT_SECRET`（已存在则保留，除非显式传 `--jwt-secret`）、可重复 `daemon-reload`。

**不含数据库初始化**（本次范围外）。

### 4.3 前端 `install.sh`

**用法**

```bash
sudo zg-homework-web/scripts/install.sh \
  --web-prefix /homework \
  --api-prefix /homework_api \
  --api-upstream 127.0.0.1:8000 \
  --deploy-dir /var/lib/zg-homework-web
```

**参数**

| 参数 | 默认 | 说明 |
|---|---|---|
| `--web-prefix` | `/homework` | 前端路径前缀（须以 `/` 开头并以 `/` 结尾） |
| `--api-prefix` | `/homework_api` | 后端路径前缀（须以 `/` 开头并以 `/` 结尾） |
| `--api-upstream` | `127.0.0.1:8000` | 后端上游，必须是 `127.0.0.1:PORT` |
| `--deploy-dir` | `/var/lib/zg-homework-web` | 前端产物根目录 |
| `--no-reload` | 关 | 生成片段后不 reload nginx |
| `--print-only` | 关 | 只打印片段内容到 stdout，不写文件（供人工核对） |

**行为**

1. 建 `<deploy-dir>/releases/`（`0755`）。
2. 生成 `/etc/nginx/conf.d/zg-homework.conf`（`0644`），内容见 §4.4。
3. `nginx -t` 校验（失败则保留原文件并报错退出，不 reload）。
4. 除非 `--no-reload`，执行 `nginx -s reload`（或 `systemctl reload nginx`）。
5. 提示：主配置需在 `server` 块内 `include /etc/nginx/conf.d/*.conf;`；若未 include，`nginx -t` 通过但片段不会生效——脚本需检测主配置是否 include 了 `conf.d`，未 include 时给出明确告警。

**幂等**：片段内容按参数生成，参数不变则重复执行为 no-op（先比对，相同则跳过写入与 reload）。

### 4.4 nginx 片段内容

```nginx
# /etc/nginx/conf.d/zg-homework.conf
# 由 zg-homework-web/scripts/install.sh 生成；只含 location 块，不得加入 server 块。
# 同域名多项目共存时，本项目独占 /homework/ 与 /homework_api/ 两个前缀。

location /homework/ {
    alias /var/lib/zg-homework-web/current/;
    index index.html;
    try_files $uri $uri/ /homework/index.html;
}

location /homework_api/ {
    proxy_pass http://127.0.0.1:8000;      # 不带末尾斜杠：服务端路由自带 /homework_api 前缀，不剥除
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 12m;              # 作业文件上传
    proxy_read_timeout 60s;
}
```

要点：
- `alias` 必须以 `/` 结尾，否则路径拼接出错。
- `try_files` 的回退值是 URI（`/homework/index.html`），nginx 重新匹配 `location /homework/` 后由 `alias` 解析为 `current/index.html`。
- `proxy_pass` 不带末尾 `/`：服务端路由本身带 `/homework_api` 前缀，带了会被剥掉导致 404。
- `/homework_api/` 不会被 `/homework/` 抢匹配（后者要求斜杠结尾）。

### 4.5 `web_deploy.sh`

**职责**：取得前端产物 → 发布到 `releases/<版本>` → 原子切换 `current` → `nginx -t` → reload。

**两种输入模式**（生产机通常不装 Node，默认走模式 A）：

| 模式 | 用法 | 依赖 | 适用 |
|---|---|---|---|
| A. 从静态包发布（默认） | `web_deploy.sh --package <xxx>.tar.gz` | 仅 tar / nginx | 生产机无 Node；构建在开发机或 CI 完成 |
| B. 在服务器本机构建 | `web_deploy.sh --build` | Node ≥ 20 + `node_modules` | 服务器已有依赖、需即时重建 |

**模式 A 细节**（对应现有 `web_package.sh` 的产物）：

- 输入是 `web_package.sh` 生成的静态包，包内顶层目录为 `zg-homework-web-static/`，内容为 `index.html` + `assets/`（已含 `base=/homework/` 与 `VITE_API_BASE_URL=/homework_api`）。
- 解包时取包内**唯一**顶层目录的内容；若包内顶层目录不唯一或缺失，判为非法包并中止。
- 解包目标 `<deploy-dir>/releases/<版本>/`，解包后校验 `index.html` 存在。
- 包内若含符号链接、特殊文件或路径穿越（`../`）条目，一律拒绝——与 `web_package.sh` 的安全约束对齐。

**模式 B 细节**：等价于 §4.5 原流程的第 1–2 步——`tsc --noEmit --incremental false` → `vite build --mode production --base /homework/ --outDir <deploy-dir>/releases/<版本> --emptyOutDir`，注入 `VITE_API_BASE_URL=/homework_api`；前置检查 `node ≥ 20` 与 `node_modules/.bin/{tsc,vite}` 可执行。

**共同流程**

1. 前置检查：`<deploy-dir>/releases` 存在（否则提示先跑 web `install.sh`）；模式 B 另需 node 依赖检查。
2. 版本目录名：`web-<UTC 时间戳>-<内容短哈希>`，同一目录内唯一且可排序。
3. 校验产物存在 `index.html`；写入归属标记 `.web-run-owner`（内容 = 源码检出目录绝对路径 + `\n`；模式 A 下取包内记录的构建来源，取不到则写 `<unknown>`），与 `web_run.sh` 的标记格式一致，保证两套脚本不会互相误认 `current`。
4. `nginx -t`：失败则**中止**，不切换 `current`、不 reload，删除本次版本目录。
5. 原子切换：在 `<deploy-dir>` 下建临时符号链接指向新版本目录，`os.replace` 覆盖 `current`（与 `web_run.sh` 的 `publish()` 同一手法）。
6. `nginx -s reload`（`--no-reload` 时跳过）。
7. 失败处理：任一步骤异常且已切换 `current`，把 `current` 指回旧版本并 reload 恢复，打印「已恢复上一版本」。
8. 清理策略：**不自动删除**旧版本目录（避免删掉正在被访问的 inode）；打印保留列表，由运维按需清理。

**用法**

```bash
# 模式 A：上传静态包后发布（生产机）
zg-homework-web/scripts/web_deploy.sh --package /tmp/zg-homework-web-static-20261113-101500.tar.gz

# 模式 B：服务器本机构建并发布
zg-homework-web/scripts/web_deploy.sh --build
```

**与 `web_run.sh` 的关系**：两者共用 `<deploy-dir>`、`releases/`、`current` 与 `.web-run-owner` 标记格式。`web_run.sh` 保持独占 nginx 模式不变，本方案不使用它；两套脚本的产物互不破坏。

**不写 `/etc/nginx/`**：reload 只触发，不改配置。改配置是 web `install.sh` 的职责。

### 4.6 打包产物到生产的完整链路

这是「打包脚本」与「部署方案」的衔接点，也是本方案对外的主流程：

```
开发机 / CI                                   生产机（多项目共存）
──────────                                    ──────────────────
git checkout main
cd zg-homework-server
./scripts/server_package.sh
  → zg-homework-tests/tar/zg-homework-server-<ts>.tar.gz
   （含 app/ + requirements.txt + scripts/，含 install.sh；不含任何凭据）
                                    scp  ──▶  解压到 /data/apps/zg-homework-server
                                              sudo ./scripts/install.sh \
                                                   --server-dir /data/apps/zg-homework-server \
                                                   --api-port 8000 --database-url … 
                                              sudo sh ./scripts/server_run.sh check

cd zg-homework-web
./scripts/web_package.sh
  → zg-homework-tests/tar/zg-homework-web-static-<ts>.tar.gz
   （base=/homework/，API 前缀=/homework_api）
                                    scp  ──▶  sudo ./scripts/install.sh --api-upstream 127.0.0.1:8000
                                              ./scripts/web_deploy.sh --package <上传的包>
```

要点：
- 两个打包脚本的产物**均不含凭据**：服务端包排除 `.env` 与 admin 密码哈希；前端静态包只含构建产物。
- 服务端包内的 `scripts/install.sh` 与仓库内同一份脚本——打包脚本的白名单需要相应补上 `scripts/install.sh`（见 §10 第 1 步）。
- 前端包内不需要 `install.sh`（安装只需在生产机做一次），但为便于「解包即装」，web 包**不**强行带上脚本，保持产物最小。


---

## 5. 顺带修复的既有缺陷

| 缺陷 | 位置 | 修复 |
|---|---|---|
| `JWT_SECRET=需要ti'huan` 含单引号，而 `server_run.sh` 的配置校验拒绝值中 `'"\$` → 该模板**永远无法通过校验** | `zg-homework-server/scripts/production.env.example` | 改为无引号占位符 `__REPLACE_ME__`（`server_run.sh` 的占位符检查会识别 `__…__`） |
| `CORS_ORIGINS=http://localhost:5173` 在同域反代下无意义且指向开发环境 | 同上 | 改为 `__REPLACE_ME__` 或留空注释，由 `install.sh --cors-origins` 注入 |
| `CLAUDE.md` 顶部称「已移除根 Makefile、开发/初始化脚本、部署/打包脚本和文档验收脚本」，但 `scripts/server_package.sh`、`web_package.sh`、`init_check.sh`、`server_run.sh`、`web_run.sh` **确实存在**且有契约测试 | `CLAUDE.md` | 修正为实际情况，并补充新增的 `install.sh`、`web_deploy.sh` |
| `CLAUDE.md` 描述的 `install.sh`、`deploy/README-DEPLOY.md`、根 `Makefile`、`scripts/dev.sh`、`scripts/init.sh`、`zg-homework-docs/scripts/acceptance_check.py`、`independence_check.py` **均不存在** | `CLAUDE.md` | 删除或改写这些失效引用，避免误导 |

---

## 6. 数据库初始化（文档保留手工步骤，脚本不做）

install 脚本**不**执行数据库初始化。文档给出两种既有路径：

| 路径 | 命令 | 内容 | 适用 |
|---|---|---|---|
| 部署 | `python -m app.seed.initial_data` | `create_all()` + 积分规则 + admin | 生产部署 |
| 本地联调 | `python -m app.seed.initial_data`（同上，另含班级/测试账号/家长绑定/成语题库） | 同上，更全 | 开发 |

`app.seed.initial_data` 幂等，重复执行不重复插入，且**不覆盖已存在的 admin 密码**。

> 注意：`create_all()` 只建缺失的表，不给已有表加列。涉及表结构的升级需执行 `app/seed/migrate_*.py` 中的迁移脚本，迁移前备份数据库。

---

## 7. 文档重写：《生产部署打包方案.md》

重写为以下章节：

1. **多项目共存拓扑** —— 同域名 + 路径前缀模型；本项目的资源归属清单；写入纪律。
2. **路径前缀与端口分配** —— 分配表模板；`/homework/`、`/homework_api/`、`127.0.0.1:8000`；多项目间的端口与前缀不冲突约定。
3. **目录与数据规划** —— §3 全表；上传数据外置的原因（升级覆盖代码不丢文件）。
4. **服务端部署** —— `install.sh` 一键安装；等价手工步骤（渲染 unit / 生成 env / 建目录 / 建 venv / daemon-reload）；`server_run.sh` 的 check/status/start/stop/restart 用法。
5. **前端部署** —— `install.sh` 生成片段 + `web_deploy.sh` 发布；`web_package.sh` 产出静态包的使用场景。
6. **共享 nginx 片段规范** —— §4.4 内容；片段与主配置的 include 约定；reload 纪律；主配置模板示例。
7. **数据库初始化** —— §6。
8. **TLS 与证书** —— 同域名共用一张证书，由运维统一管理；本项目不申请、不续期；HTTP→HTTPS 由主配置负责。
9. **升级、回滚与备份** —— 后端：备份数据库 → 停服 → 覆盖代码 → `init_check.sh` → 改配置 → `server_run.sh restart` → 验证；前端：`web_deploy.sh` 发布失败自动回滚；备份项清单（数据库、`/var/lib/zg-homework/`）。
10. **日常更新流程** —— 补完现有 `-- TODO`：开发 → 本地验证 → `main` 分支打包 → 上传 → 安装 → 验证 → 回滚预案。
11. **验证清单与故障对照表** —— §8。
12. **脚本职责对照表** —— §4.1。

全文所有端口、worker 数、路径必须与项目实际对齐：8000、`--workers 1`、服务端 `WorkingDirectory` = 检出目录、上传数据外置、共享 nginx + 路径前缀。

---

## 8. 验证清单与故障对照

```bash
# 1. 后端存活
sudo systemctl status zg-homework-server
curl -i -X POST http://127.0.0.1:8000/homework_api/health    # 200
sudo sh zg-homework-server/scripts/server_run.sh check          # 全套契约校验通过

# 2. 前端静态（经共享 nginx）
curl -I https://xxx.com/homework/                    # 200 text/html
curl -I https://xxx.com/homework/assets/<hash>.js    # 200

# 3. 接口经共享 nginx 转发
curl -i -X POST https://xxx.com/homework_api/health  # 200
curl -i https://xxx.com/homework_api/me              # 401（未登录，属正常）

# 4. SPA 深链刷新不 404
# 浏览器访问 https://xxx.com/homework/teacher → 正常渲染

# 5. 前端产物与 current 指向
readlink -f /var/lib/zg-homework-web/current
ls /var/lib/zg-homework-web/current/index.html
```

| 现象 | 原因 |
|---|---|
| `/homework/` 403/404 | `alias` 末尾缺 `/`；`current` 悬空；`releases` 目录权限不对 |
| 刷新子路由 404 | `try_files` 回退值未带 `/homework/` 前缀 |
| 接口 404 | `proxy_pass` 多了末尾 `/`，前缀被剥掉 |
| 接口 502 | 后端未启动或端口不是 8000；`journalctl -u zg-homework-server -f` |
| 页面白屏 / 资源 404 | Vite `base` 未为 `/homework/`，或 Router `basename` 缺失 |
| 片段不生效 | 主配置的 server 块未 `include /etc/nginx/conf.d/*.conf;` |
| `server_run.sh check` 报「配置格式不受支持」 | env 值含 `'"\$`、重复键、或含未替换的 `__…__` 占位符 |
| 上传文件丢失 | `UPLOAD_DIR`/`PRIVATE_HOMEWORK_DIR` 落在代码目录内（被升级覆盖） |
| 多 worker 下成语接龙会话丢失 | `--workers` 大于 1 |

---

## 9. 测试策略

新增两个测试文件，临时目录沿用项目约定放在仓库 `docs/` 下：

### 9.1 `zg-homework-tests/test_install_scripts.py`

- 在隔离目录中运行两个 `install.sh`（用假 `systemctl`/`nginx`/`openssl`），断言：
  - systemd 单元渲染后**不含**任何 `__…__` 占位符；
  - `ExecStart` 逐字等于 `<python> -m uvicorn app.main:app --host 127.0.0.1 --port <port> --workers 1`；
  - `EnvironmentFile=/etc/zg-homework-server/env`、`Type=simple`、`KillMode=control-group`、`Environment=` 仅两个既定键；
  - env 文件权限 `0640`、属主 `root:<service-group>`；值不含 `'"\$`；无未替换占位符；
  - 数据目录已建且在 `--server-dir` 之外；
  - nginx 片段只含两个 `location`、**不含** `server {` 块；`proxy_pass` 不带末尾 `/`；`alias` 带末尾 `/`；
  - 非法参数（端口越界、`--database-url` 非 `mysql+pymysql://`、`--data-dir` 落在 `--server-dir` 内、缺 `--database-url`）一律非零退出且不写文件；
  - 幂等：二次执行不报错、`JWT_SECRET` 不被覆盖；
  - 产物中不含明文凭据回显到 stdout（`--jwt-secret` 传入的值不出现在输出里）。

### 9.2 `zg-homework-tests/test_web_deploy.py`

- 假 `node`/`tsc`/`vite`/`nginx`/`systemctl`：
  - **模式 A（从包发布）**：给定合法静态包 → 解包到新版本目录 → `current` 切换 → reload；包内顶层目录不唯一 / 缺 `index.html` / 含符号链接 / 含 `../` 路径穿越条目 → 拒绝且不切换 `current`、不 reload；
  - **模式 B（服务器构建）**：`tsc` 失败 → 不构建、不切 `current`、不 reload；
  - `nginx -t` 失败 → **不切 `current`、不 reload**，旧版本目录保持为 current；
  - 成功 → `current` 指向新版本目录、写入 `.web-run-owner`、执行 reload；
  - 切换后 reload 失败 → 自动回滚 `current` 到旧版本；
  - 产物目录名唯一、可排序；旧版本目录不被自动删除。
- 模式 A **不需要** Node 与 `node_modules` 即可完成发布（断言未调用 `tsc`/`vite`）。

### 9.3 不动的测试

`zg-homework-tests/test_run_scripts.py`、`test_production_contract.py`、`test_package_scripts.py` 保持不变（`web_run.sh`、`server_run.sh`、两个打包脚本均不改行为）。

---

## 10. 实施顺序

1. 修 `production.env.example` 的两处模板缺陷（§5）；把 `scripts/install.sh` 加入 `server_package.sh` 的 `FILES` 白名单（§4.6）。
2. 写服务端 `install.sh` + 契约测试（`test_install_scripts.py`）。
3. 写前端 `install.sh` + 契约测试。
4. 写 `web_deploy.sh`（模式 A + 模式 B）+ 契约测试（`test_web_deploy.py`）。
5. 重写《生产部署打包方案.md》（§7）。
6. 同步 `CLAUDE.md`（§5）。
7. 全量跑 `zg-homework-tests/` 与 `docs/` 下的既有测试。

---

## 11. 非目标

- 不做 Docker / docker-compose 路径（仓库中 Docker 路径本就没有 compose 支撑）。
- 不做 TLS 证书的申请与续期。
- 不做数据库迁移框架（沿用 `app/seed/migrate_*.py`）。
- 不改 `web_run.sh`（独占 nginx 模式保留，本方案不使用）。
- 不做多机部署、负载均衡、自动扩缩容。
