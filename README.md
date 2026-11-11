# zg-tsp

学校兴趣培养积分系统 —— 聚合仓库。

> **本仓库已拆分为 5 个独立仓库**（决策 6：四模块拆独立仓库）。
> 这里的代码是拆分时的**快照**，用于追溯与聚合检出；日常开发请在各自独立仓库进行。

## 五个独立仓库

| 仓库 | 内容 | 技术栈 |
|------|------|--------|
| `zg-tsp-server` | 服务端 | Python 3.12 / FastAPI / SQLAlchemy 2.0 / MySQL 8 |
| `zg-tsp-web` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 |
| `zg-tsp-ios` | iOS 移动端 | Flutter 3.47 / Dart 3.13 |
| `zg-tsp-android` | Android 移动端 | Flutter 3.47 / Dart 3.13 |
| `zg-tsp-docs` | **文档与契约**（PRD、配置、验收脚本） | Markdown / Python |

各仓库已生成在 `../zg-tsp-repos/`（同级目录），可独立检出、提交、发版。

## 拆分方式

用 `git subtree split` 保留完整提交历史：

```bash
git subtree split --prefix=zg-tsp-server -b split/zg-tsp-server
git subtree split --prefix=zg-tsp-web    -b split/zg-tsp-web
git subtree split --prefix=zg-tsp-ios    -b split/zg-tsp-ios
git subtree split --prefix=zg-tsp-android -b split/zg-tsp-android
git subtree split --prefix=zg-tsp-docs   -b split/zg-tsp-docs
```

各分支根目录即模块根目录，`git clone` 后无需再调整路径。

## 聚合检出（联调用）

各模块仍可单独检出、单独安装依赖、单独启动、单独打包（PRD 2.2.1）。
聚合检出仅为联调方便：

```
workspace/
├── zg-tsp-docs/       ← 契约与验收脚本
├── zg-tsp-server/
├── zg-tsp-web/
├── zg-tsp-ios/
└── zg-tsp-android/
```

```bash
# 终端 1：服务端
cd zg-tsp-server && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：Web 端（Vite 代理 /homework_api → 127.0.0.1:8000（保留前缀））
cd zg-tsp-web && npm run dev

# 终端 3：验收脚本
python zg-tsp-docs/scripts/acceptance_check.py
python zg-tsp-docs/scripts/independence_check.py
```

## 快速开始（服务端）

```bash
cd zg-tsp-server
pip install -r requirements.txt
cp .env.example .env          # 按需改 DATABASE_URL / JWT_SECRET

python -m app.seed.initial_data          # 建表 + 种子
python -m app.seed.apply_comments        # 补齐字段中文注释

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：`POST /homework_api/health` → `{"code":0,"message":"ok","data":{"status":"ok","env":"dev"}}`（`env` 随环境而变）

### 部署用数据库初始化

部署到空机器时，一条命令完成「建库 → 建表 → 写积分规则及批改档位 → 建 admin」：

```bash
./scripts/init.sh              # 幂等，可重复执行
./scripts/init.sh --drop       # 先删库重建（危险，需二次确认）
```

它导入的是 `zg-tsp-docs/sql/init.sql` —— 该文件由 `python -m app.seed.export_ddl`
从 ORM 生成，含全部表的中文 COMMENT。admin 初始密码取 `ADMIN_INIT_PASSWORD`
环境变量，未设则随机生成。仅在本次密码生效时显示随机密码或提示使用了环境变量，首登强制改密。已有正常密码不会被覆盖，`ADMIN_INIT_PASSWORD` 不能用于强制重置密码；已有 admin 的密码哈希恰为 `__ADMIN_BCRYPT_HASH__` 时会被修复。直接导入未经替换的 SQL 会创建表和规则，但不会创建 admin；应使用初始化脚本，或先将占位符替换为有效 bcrypt 哈希再导入。

需要联调数据（测试账号、班级、成语题库）时，另跑 `python -m app.seed.initial_data`。

## 功能范围

**四角色**（admin / teacher / student / parent）× **两平台**（移动端 + Web）全覆盖。

| 模块 | Phase | 状态 |
|------|-------|------|
| 服务端 | P1 认证（JWT + 老师邀请码一码一用） | ✅ |
| 服务端 | P1b MySQL 14 张表 + 全字段中文注释 | ✅ |
| 服务端 | P1.5 admin 基础（邀请码 / 用户 / 统计） | ✅ |
| 服务端 | P1.6 积分规则管理 + 规则缓存 + 积分发放 | ✅ |
| 服务端 | P2 班级与作业（打点 / 迟交 / 用时） | ✅ |
| 服务端 | P3 签到与排行榜 | ✅ |
| 服务端 | P4 家长绑定与扣分 | ✅ |
| 服务端 | P5 课后阅读（心跳防挂机） | ✅ |
| 服务端 | P6 数独 + 成语接龙 + 题库管理 | ✅ |
| Web | P7 四角色页面 | ✅ |
| 移动端 | P8 四角色页面（Flutter） | ✅ |
| 全局 | P9 联调验收 | ✅ |

## 验证状态

| 检查项 | 结果 |
|--------|------|
| 服务端 pytest | 294 passed |
| PRD 业务验收（第 12 节） | 27/27 |
| 模块独立性检查 | 10/10 |
| Web `tsc` + `vite build` | ✅ |
| 移动端 `flutter analyze` / `test` | ✅ 两端均无问题 |

## 文档

完整需求与契约见 [`zg-tsp-docs/sys_doc/PRD.md`](zg-tsp-docs/sys_doc/PRD.md)。
配置项见 [`zg-tsp-docs/sys_doc/config.md`](zg-tsp-docs/sys_doc/config.md)。
