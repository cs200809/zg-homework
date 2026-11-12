# zg-tsp-web

学校兴趣培养积分系统 —— Web 管理端模块（学生 / 家长 / 老师 / admin 全覆盖）。

## 独立性

当前聚合检出包含 `zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/` 三个模块；微信小程序是仓外独立仓库。Web 模块也可单独检出、启动和打包，不依赖其他模块源码：

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

## 打包

```bash
npm run build          # 产出 dist/，纯静态文件

docker build -t zg-tsp-web:1.0.0 .
docker run -d -p 8080:80 zg-tsp-web:1.0.0
```

`dist/` 是静态文件；默认构建使用同域 `/homework_api`，部署时还需将此前缀原样反代到服务端。Docker 内 Nginx 默认指向 `server:8000`，需自行提供可解析的服务端网络。

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
python zg-tsp-docs/scripts/independence_check.py
```

业务验收需要服务端运行在 `127.0.0.1:8000`，使用已有 admin 密码及装有服务端依赖的 Python：

```bash
ACCEPTANCE_ADMIN_PASSWORD='<已有 admin 密码>' .venv/bin/python zg-tsp-docs/scripts/acceptance_check.py
```

业务验收调用真实接口并留下持久数据，应使用隔离环境；脚本不会重置 admin，跳过修改共享积分规则和删除数据的验收项。服务端 pytest 也会写入和可能删除数据，必须指向专用隔离 MySQL 库，详见服务端 README。独立性检查只覆盖 server 和 web，小程序不在本检出内。

## 开发进度

- [x] P0 骨架：构建配置、API 客户端、环境变量、Dockerfile + Nginx
- [x] P7 四角色页面：登录注册改密、学生端 7 页、老师端 4 页、
      admin 端 7 页（含成语题库管理）、家长端 2 页