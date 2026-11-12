# zg-homework-web

学校兴趣培养积分系统 —— Web 管理端模块（学生 / 家长 / 老师 / admin 全覆盖）。

## 独立性

当前聚合检出包含 `zg-homework-server/`、`zg-homework-web/`、`zg-homework-docs/` 三个模块；微信小程序是仓外独立仓库。Web 模块也可单独检出、启动和打包，不依赖其他模块源码：

- 与服务端**仅通过 HTTP 接口**通信，不引用服务端源码
- 依赖自封闭：`package.json` 为唯一依赖清单
- 配置外置：`VITE_API_BASE_URL` 构建期注入，代码中不硬编码地址
- 服务端不可用时前端仍可启动，接口调用降级提示，不崩溃

## 启动

```bash
# 1. 安装依赖
npm install

# 2. 配置（可选项，仓库内 .env.development 已提供默认值）
# 按需编辑或使用 .env.local 覆盖，不要覆盖已有配置

# 3. 运行（默认 http://localhost:5173）
npm run dev
```

开发环境走 Vite 代理（`/homework_api` → `VITE_PROXY_TARGET`，默认 `http://127.0.0.1:8000`，保留路径前缀），避免跨域。

## 源码部署包

```bash
./scripts/web_package.sh  # 默认输出到 ../zg-homework-tests/tar/
./scripts/web_package.sh -o /已有目录/zg-homework-web.tar.gz
```

打包需要 Python 3。输出路径须位于模块目录之外，且目标文件不能已存在。归档读取脚本所在模块当前工作树，包括未提交源码；不会拉取代码或切换分支。按仓库约定，生产打包应在经验证的 `main` 检出执行，打包期间不要修改源码。

归档包含 `src/` 源码及资源、构建配置、依赖清单及锁文件、Nginx/Docker 配置、README 和运行及打包脚本；不包含测试、临时文件、依赖目录、构建产物或 `.env` 文件。部署时须自行审核运行环境；Vite 客户端变量会进入浏览器代码，不能存放密钥。解压到新目录后用 Node 20+ 安装依赖，按需另行准备配置并由运维配置独立 systemd/Nginx。

**注意：** 打包仅收集文件，不验证或修复运行脚本。当前运行脚本仍存在生产安全问题，且尚未完成 Linux/systemd 实机验证；完成修复和隔离验证后才可生产部署。

## 构建与 Docker 打包

```bash
npm run build          # 产出 dist/，纯静态文件

docker build -t zg-homework-web:1.0.0 .
docker run -d -p 8080:80 zg-homework-web:1.0.0
```

`dist/` 是静态文件；默认构建使用同域 `/homework_api`，部署时还需将此前缀原样反代到服务端。Docker 内 Nginx 默认指向 `server:8000`，需自行提供可解析的服务端网络。

## Linux 生产运行（独立 Nginx 实例）

`scripts/web_run.sh` 仅管理预先配置的 **专用** systemd unit，不管理、修改或重启系统共享 Nginx。需要 Linux、systemd、Python 3、`ss`、Node >= 20、npm、已安装的 Web 依赖及 Nginx；运行账号需要 systemd 控制权限、读取监听进程及其 `/proc/*/cgroup` 的权限，以及发布目录写权限。脚本按自身路径识别当前检出，不拉取或切换代码。部署目录和配置必须由可信管理员维护，不得允许其他用户修改；脚本不是权限隔离工具。

默认值是 `WEB_UNIT=zg-homework-web.service`、`WEB_PORT=8080`、`WEB_DEPLOY_DIR=/var/lib/zg-homework-web`、`WEB_NGINX_CONFIG=/etc/zg-homework-web/nginx.conf`、`WEB_NGINX_BIN=/usr/sbin/nginx`、`WEB_API_UPSTREAM=127.0.0.1:8000`。覆盖时必须同步调整下面的 unit 和配置；路径必须是绝对的、无符号链接且只包含字母、数字、`_`、`-`、`.`、`/`。先创建发布目录及其 `releases` 子目录，发布目录不得位于检出中，保证 Nginx 用户可读取目录和产物。不要预建 `current`，它是脚本管理的符号链接。已有 `current` 必须指向同一检出创建的 release。

由运维手动配置以下专用 unit（把 `/absolute/path/zg-homework-web` 换为当前检出的物理路径），不要增加 ExecStartPre/Post、ExecStop/Post、ExecReload、RootDirectory 或 RootImage。该服务只能运行此专用 Nginx，不能指向共享 Nginx。unit 修改后由运维执行 `systemctl daemon-reload`。

```ini
[Unit]
Description=Homework web dedicated nginx
[Service]
Type=simple
WorkingDirectory=/absolute/path/zg-homework-web
ExecStart=/usr/sbin/nginx -c /etc/zg-homework-web/nginx.conf -g "daemon off;"
[Install]
WantedBy=multi-user.target
```

`/etc/zg-homework-web/nginx.conf` 必须与下文完全一致（包括换行），以便脚本在控制服务之前验证归属与代理约定。修改变量时替换对应值；`WEB_API_UPSTREAM` 仅接受 `127.0.0.1:端口`。专用实例只监听本机，公网 TLS、域名和前置反代由运维另行配置。API 代理的 `proxy_pass` 没有末尾斜线，保留 `/homework_api/` 前缀。

```nginx
worker_processes 1;
pid /var/lib/zg-homework-web/nginx.pid;
error_log stderr;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log /dev/stdout;
    server {
        listen 127.0.0.1:8080;
        root /var/lib/zg-homework-web/current;
        index index.html;
        client_max_body_size 12m;
        location /homework_api/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        location / { try_files $uri $uri/ /index.html; }
    }
}
```

```bash
./scripts/web_run.sh check
./scripts/web_run.sh status
./scripts/web_run.sh start
./scripts/web_run.sh restart
./scripts/web_run.sh stop
journalctl -u zg-homework-web.service -n 100 --no-pager
```

`check` 和 `status` 不修改文件或控制服务；`status` 对服务未运行、Web 或 API 健康检查失败返回非零，分别报告 Web 和 API 状态。`start` 在已运行时不构建也不重启；更新代码使用 `restart`。每次实际启动或重启都会执行非增量 TypeScript 检查和 Vite 生产构建，并固定同域 API 地址。新产物先写入唯一 release，成功后原子切换 `current`；构建失败不会切换或停止已有服务。启动失败会恢复原有链接（首次部署没有旧链接），但服务可能仍处于失败或停止状态，需要运维检查日志并手动启动。API 不健康返回非零，不代表 Web 启动失败；健康接口也不保证数据库持续可用。

旧 release 和失败的构建目录不会自动删除。回退时，由运维确认旧 release 属于该检出、保留其 `.web-run-owner` 文件，在停用并检查相应服务后原子替换 `current` 指向该目录，再由运维启动专用 unit；不要使用 `restart` 回退，因为它会重新构建。手工清理前确认目录归属和未被使用，脚本不会清理历史目录。部署只验证约定的配置和服务，不验证前置代理、TLS、API 后端或并发修改发布目录的外部程序。按仓库发布约定应从已验证的 `main` 检出部署。切换发布后，仍使用旧 HTML 的浏览器可能无法加载旧版本的哈希资源；应安排维护窗口或由前置服务提供旧版本静态资源。

## 环境（测试 + 生产）

| 文件                 | 用途       | API 地址                 |
|--------------------|----------|------------------------|
| `.env.development` | 开发/测试构建 | `/homework_api`（Vite 代理） |
| `.env.production`  | 生产构建 | `/homework_api`（Nginx 代理） |

生产默认同域反代，直连其他域名时须包含 `/homework_api` 前缀并配置 CORS。两个文件均不含敏感信息，可提交；
`.env.local` 为本地覆盖，已在 `.gitignore` 中排除。

## 目录结构

```
src/
├── api/          HTTP 客户端（client.ts：统一 POST、错误码、降级）
├── pages/
│   ├── common/   登录/注册/强制改密
│   ├── student/  学生端
│   ├── parent/   家长端
│   ├── teacher/  老师端（桌面形态：完整表格/抽屉/批量）
│   └── admin/    admin 端（桌面形态：完整表格/抽屉/批量）
├── components/
│   └── AdminLayout.tsx  主布局：侧边菜单按角色渲染
├── store/
│   └── auth.ts           Zustand 登录态（token 存 localStorage）
├── router/
│   └── index.tsx         路由 + 角色守卫
└── utils/        工具函数
```

## 四角色页面（PRD 第 9 节）

| 角色   | 路由前缀   | 页面                                                    |
|--------|-----------|---------------------------------------------------------|
| 学生   | `/student` | 首页、作业、阅读、游戏、排行榜、我的积分                    |
| 老师   | `/teacher` | 班级管理、作业管理、完成情况、文章管理                    |
| admin  | `/admin`  | 数据概览、邀请码、用户、积分规则、文章、班级总览、**成语题库** |
| 家长   | `/parent`  | 孩子列表/绑定、积分明细、积分消耗                          |

登录后按角色自动分流；admin 未改密时强制跳转改密页（PRD 5.1）。

## 验收

从聚合仓库根目录运行静态模块独立性检查，无需服务端或数据库：

```bash
python zg-homework-docs/scripts/independence_check.py
```

业务验收需要服务端运行在 `127.0.0.1:8000`，使用已有 admin 密码及装有服务端依赖的 Python：

```bash
ACCEPTANCE_ADMIN_PASSWORD='<已有 admin 密码>' .venv/bin/python zg-homework-docs/scripts/acceptance_check.py
```

业务验收调用真实接口并留下持久数据，应使用隔离环境；脚本不会重置 admin，跳过修改共享积分规则和删除数据的验收项。服务端 pytest 也会写入和可能删除数据，必须指向专用隔离 MySQL 库，详见服务端 README。独立性检查只覆盖 server 和 web，小程序不在本检出内。

## 开发进度

- [x] P0 骨架：构建配置、API 客户端、环境变量、Dockerfile + Nginx
- [x] P7 四角色页面：登录注册改密、学生端 7 页、老师端 4 页、
      admin 端 7 页（含成语题库管理）、家长端 2 页