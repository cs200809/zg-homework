# 学习兴趣培养积分系统 — 完整 PRD（v2.2）

> 版本：v2.2（移除 Flutter 移动端，平台维度改为 Web + 小程序）  
> 技术栈：React + Ant Design 前端 / Python FastAPI 后端 / JWT 认证  
> 接口约定：**业务接口使用 POST，参数走 Body**；实际路径统一以 `/homework_api` 开头，详见 3.1 节
> 文档目的：作为 LLM 直接开发项目的唯一依据

---

## 0. 变更记录

### v2.2（移除 Flutter 移动端）

| # | 变更项 | 说明 |
|---|--------|------|
| 1 | 下线 Android / iOS 移动端 | Flutter 双端（`zg-tsp-android`、`zg-tsp-ios`）停止维护，独立仓库已删除；源码仍保留在聚合仓库历史提交 `7bf7dd0` 之前，可随时恢复 |
| 2 | 平台维度改为 Web + 小程序 | 第 9 节的「移动端」列整体替换为「小程序端」；微信小程序为原生小程序（WXML/WXSS/JS），独立仓库，位于聚合检出之外，规划与验收见 [小程序.md](小程序.md) |
| 3 | 模块数量由四个降为三个 | 服务端 / Web / 文档三仓；小程序端不计入本聚合检出的模块（PRD 2.2） |
| 4 | 渠道策略调整 | 决策 7 由「移动端两个渠道」改为「Web 两套构建变量 + 小程序 dev/prod 配置」 |

> **小程序端与本 PRD 的关系**：小程序复用现有服务端，**服务端零改动**；
> 其接口清单以本 PRD 第 7 节为准，功能范围与排期以 [小程序.md](小程序.md) 为准。
> 小程序端一期覆盖学生端与家长端，老师端与 admin 端排在二期
> （属第 9.6 条的阶段性偏离，见 [小程序.md](小程序.md) §1.1）。

### v2.1（迭代：注册 / 班级码 / 阅读文档能力）

| # | 变更项 | 说明 |
|---|--------|------|
| 1 | 注册用户名改为手机号 | 格式 `^1[3-9]\d{9}$`，并校验唯一性（PRD 5.1） |
| 2 | 学生注册带**班级邀请码** | 注册时校验班级邀请码存在，注册后**自动加入班级**。班级邀请码**多学生可用**（班级属性），老师 / admin 可重新生成，旧码立即失效，已入班学生不受影响 |
| 3 | 家长注册带**学生绑定码** | 注册时校验绑定码存在，注册后**自动绑定学生**。学生绑定码**多家长可用**（学生属性），admin / 老师可重新生成，旧码立即失效，已建立的家长关系不受影响 |
| 4 | 老师邀请码维持一码一用 | 注册时消耗，`status=used`（不变） |
| 5 | admin / 老师可重新生成班级邀请码 | 新增 `POST /classes/regenerate-invite` |
| 6 | admin / 老师可重新生成学生绑定码 | 新增 `POST /classes/regenerate-bind-code` |
| 7 | 学生端可查看绑定码 | 服务端 `/auth/me` 已返回 `bind_code`；Web 新增学生端「我的」页，小程序端「我的」页已有 |
| 8 | 发布文章支持纯文本 / PDF / word | 新增 `POST /articles/create-file`（multipart），服务端抽取正文入库；`articles` 表新增 `file_url` / `file_name` / `file_type` |
| 9 | 阅读文章支持导出 PDF | 新增 `POST /articles/export-pdf`，服务端用 reportlab 排版（内置中文 CID 字体 `STSong-Light`） |
| 10 | 阅读时只读不可编辑 | 学生端无任何编辑入口，正文只读渲染（已在 Web / 小程序端落实，并加只读标识） |
| 11 | 登录后可自助修改当前账户密码 | ✅ 已完成。`POST /auth/change-password` 服务端契约已满足（新密码 ≥6 位，校验失败返回 400）；Web 端入口在右上角头像菜单与学生端「我的」页，小程序端入口在四角色通用「我的」页；验收见 `scripts/acceptance_check.py` 第 18 组断言 |
| 12 | 修复上传文件无法访问 | `app/main.py` 新增 `StaticFiles("/uploads")` 挂载（此前 `/uploads/<name>` 无对应路由，作业附件与导出文件实际 404） |

> **本版本未覆盖的既有缺口（非本次迭代范围，遗留待办）**
> - 5.8.4 列出的 `POST /admin/articles/{list,detail,update,toggle,stats}` 六个端点**服务端仍未实现**；
>   admin 端的文章管理当前走 `/articles/*` 既有路由 + 前端筛选。
> - 5.6 提出的「数独游戏规则说明」尚未在小程序端数独页内呈现。

> **码的使用规则**：班级邀请码可供多个学生使用，学生绑定码可供多个家长使用；两者重新生成后旧码立即失效。老师邀请码注册时消耗，一码一用。

### v2.0

初始版本（合并 admin 模块与权限扩展）。

---

## 1. 项目概述

### 1.1 背景

面向小学/初中场景，通过"作业签到 → 获取积分 → 兑换奖励 + 排行榜激励"的闭环，激发学生学习与阅读兴趣，同时让家长参与积分消耗管理，由超级管理员统一管理平台。

### 1.2 目标

- 学生：完成作业、阅读、小游戏获得积分，查看排行榜获得激励
- 老师：布置作业、掌握学生作业开始时间与用时、发布阅读文章
- 家长：绑定孩子，通过扣分管理孩子看手机/电视/买玩具/零食等行为
- 管理员：发放老师邀请码、管理全角色账号、维护积分规则、管理文章与全局数据

### 1.3 角色

| 角色      | 说明                  |
|---------|---------------------|
| admin   | 超级管理员，全局管理与审计，不参与业务 |
| teacher | 老师，凭邀请码注册，班级管理者     |
| student | 学生，主要使用者            |
| parent  | 家长，积分消耗管理者          |

---

## 2. 技术栈与架构

### 2.1 技术栈

- **前端**：React 18 + Vite + Ant Design 5 + React Router 6 + Axios + Zustand
- **后端**：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Uvicorn
- **数据库**：MySQL 8（字符集 utf8mb4；SQLAlchemy 2.0 + PyMySQL）
  - 建表 SQL 见 4.1 节（以服务端 `app/models/entities.py` 的 ORM 定义为准）
- **认证**：JWT（python-jose），密码 bcrypt 加密
- **文件存储**：本地 `uploads/`（预留 OSS 接口）
- **部署**：前后端分离，Nginx 反代（可选）

### 2.2 项目结构

按端/形态拆分为三个**相互独立**的模块。每个模块可单独启动、单独打包、单独发版，
任一模块的构建/发布**不影响**其他模块——彼此唯一的耦合是服务端接口契约。

- zg-tsp-server 服务端模块
- zg-tsp-web Web 管理端模块
- zg-tsp-docs 文档与契约模块（PRD、配置、验收脚本）

> **小程序端**：微信原生小程序（WXML/WXSS/JS），**独立仓库，位于本聚合检出之外**，
> 不参与本目录的拆分与联调。其规划见 [小程序.md](小程序.md)。

```
workspace/                            # 三个独立仓库同级检出（联调用）
├── zg-tsp-docs/                      # 文档与契约（PRD、配置、验收脚本）
│   ├── sys_doc/
│   │   ├── PRD.md
│   │   └── config.md
│   └── scripts/
│       ├── acceptance_check.py       # 业务验收
│       └── independence_check.py    # 独立性检查
│
├── zg-tsp-server/                    # 服务端（FastAPI）
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/                  # auth, classes, homework, checkin,
│   │   │                             # points, articles, games, parent, admin
│   │   ├── services/                 # point_rule_service, point_service, anti_cheat
│   │   ├── utils/                    # jwt, deps(权限依赖)
│   │   ├── seed/                     # admin + point_rules 初始化
│   │   └── uploads/
│   ├── requirements.txt
│   ├── .env.example                  # 配置样例（不含真实密钥）
│   └── Dockerfile
│
└── zg-tsp-web/                       # Web 管理端（React 18 + Vite）
    ├── src/
    │   ├── api/
    │   ├── pages/
    │   │   ├── admin/                # 邀请码/用户/规则/文章/班级/概览
    │   │   ├── teacher/              # 班级/作业/文章/积分概览
    │   │   └── common/               # 登录/注册/强制改密
    │   ├── components/
    │   ├── store/
    │   └── router/
    ├── .env.example                  # VITE_API_BASE_URL
    ├── package.json                  # 依赖独立，不引用其他模块
    └── Dockerfile + nginx.conf
```

> **仓库形态（决策 6）**：上述目录是**独立 git 仓库**，各自检出、提交、发版。
> 聚合检出仅为联调方便 —— 各模块始终可单独检出、单独安装依赖、单独启动、
> 单独打包（PRD 2.2.1）。

> **决策 6**：三个模块拆分为**独立仓库**发布，本目录为聚合与文档同步用；
> 接口契约以第 7 节为唯一权威来源。小程序端为第四个独立仓库，不在本聚合检出内。

#### 2.2.1 模块独立性原则

| 原则    | 说明                                                                  |
|-------|---------------------------------------------------------------------|
| 无源码依赖 | 任何模块不得 import / 引用其他模块源码；模块间**只通过 HTTP 接口**通信                       |
| 依赖自封闭 | 每个模块自带依赖清单（`requirements.txt` / `package.json`），不使用根目录统一依赖 |
| 配置外置  | 服务端配置走 `.env`；Web 走 `VITE_*` 构建变量；小程序走 `utils/config.js`。**不硬编码**任何模块地址          |
| 单独启动  | 每个模块有独立的启动命令与健康检查，可脱离其他模块单独跑起来（接口调用失败时降级提示，不崩溃）                     |
| 单独打包  | 每个模块独立构建产物、独立版本号、独立发布，互不触发重建                                        |
| 版本契约  | 服务端接口遵循向后兼容；客户端不因服务端小版本升级而必须同步发版                                    |

#### 2.2.2 各模块独立启动与打包

**zg-tsp-server**

```bash
cd zg-tsp-server
pip install -r requirements.txt
cp .env.example .env            # 按需修改
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 打包：docker build -t zg-tsp-server:1.0.0 .
```

健康检查：`POST /homework_api/health` → `{code:0, data:{status:"ok", env:...}}`

**zg-tsp-web**

```bash
cd zg-tsp-web
npm install
npm run dev                     # 开发，API 地址取 .env 的 VITE_API_BASE_URL
npm run build                   # 产出 dist/，纯静态文件
# 打包：docker build -t zg-tsp-web:1.0.0 .   （Nginx 托管 dist/）
```

部署时只需将 `dist/` 丢到任意静态服务器 / 对象存储；API 地址在构建期注入。

**小程序端**（技术栈：微信原生小程序，决策 1）

小程序端是**独立仓库**，位于本聚合检出之外，不参与本目录的拆分与联调。
构建用微信开发者工具完成（无 Gradle / Xcode / CocoaPods 依赖）。

**API 基地址**通过 `utils/config.js` 的 `API_BASE_URL` / `FILE_BASE_URL` 外置，
用 `DEV` 布尔量区分开发与生产环境（决策 7），不硬编码在业务代码里。
服务端接口契约以第 7 节为准；功能范围与排期见 [小程序.md](小程序.md)。

> - 学生端 / 家长端以移动优先布局；老师端 / admin 端以 Web 桌面端为主（见 9.1）。
> - 小程序端技术栈为**微信原生小程序**，功能范围按排期推进（决策 1、2）。
> - 服务端接口清单见第 7 节，是各客户端唯一的契约来源。
> - **跨模块集成测试**：各模块各自可单测；跨端联调在 P9 统一进行，不作为模块独立性的约束。

---

## 3. 通用约定

### 3.1 请求规范

- **路径全局约定**：本文业务接口清单、示例及后续需求中未带前缀的路径均为相对于 API 基址的路径，不是服务端根路径。服务端实际业务路由及健康检查统一以 `/homework_api` 开头，例如 `POST /auth/login` 的实际路径为 `POST /homework_api/auth/login`，`POST /health` 为 `POST /homework_api/health`。第 14 节待实现接口也遵循同一前缀，并不因此表示已经实现。
- API 基址应包含此前缀，例如 `https://api.example.com/homework_api`；将基址末尾的 `/` 与相对路径开头的 `/` 规范拼接，避免漏掉或重复前缀。反向代理应保证请求最终命中带 `/homework_api` 的服务端路径；若对外另设前缀，须明确配置映射，不可假定服务端会接受无前缀路径。
- `file_url` 保持**相对于 API 基址**的契约，例如返回 `/uploads/x.pdf`，与上述基址拼接后访问 `https://api.example.com/homework_api/uploads/x.pdf`；不要把 `/homework_api` 再写入 `file_url`，也不要直接相对于域名根路径解析。静态上传使用 `GET /homework_api/uploads/<name>`，无需鉴权，存在公开访问风险。
- API 文档和模式地址分别为 `GET /homework_api/docs`、`GET /homework_api/redoc` 和 `GET /homework_api/openapi.json`；Swagger OAuth2 回调为 `/homework_api/docs/oauth2-redirect`。它们和静态文件不是 POST 业务接口。
- 业务接口及健康检查：`POST`
- Content-Type：`application/json`；文件上传 `multipart/form-data`
- 认证：`Authorization: Bearer <token>`
- 统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- 错误码：0 成功 / 400 参数错误 / 401 未认证 / 403 无权限 / 404 不存在 / 429 限流 / 500 服务端错误

### 3.2 分页约定

Body 传 `{page, size}`，返回 `{list, total, page, size}`

### 3.3 全局安全

- 业务接口使用 POST + Body，URL 不携带业务参数；静态文件及 API 文档例外
- 密码仅走 Body，日志脱敏
- JWT 放 Header，有效期 7 天
- 写操作服务端二次校验权限与余额
- 文件上传白名单（jpg/png/pdf），≤10MB
- 用户被禁用后，JWT 依赖查库校验 `status=active`，立即失效

---

## 4. 数据模型

### 4.1 建表 SQL

```sql
-- 用户（role: admin/teacher/student/parent；status: active/disabled）
CREATE TABLE users
(
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             VARCHAR(20) UNIQUE NOT NULL,
    password_hash        VARCHAR(255)       NOT NULL,
    role                 VARCHAR(10)        NOT NULL,
    nickname             VARCHAR(30),
    avatar               VARCHAR(255),
    class_id             INTEGER,
    bind_code            VARCHAR(8), -- 学生绑定码（家长绑定用）
    total_points         INTEGER     DEFAULT 0,
    status               VARCHAR(10) DEFAULT 'active',
    must_change_password BOOLEAN     DEFAULT 0,
    created_at           DATETIME    DEFAULT CURRENT_TIMESTAMP
);

-- 班级
CREATE TABLE classes
(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR(50)       NOT NULL,
    invite_code VARCHAR(8) UNIQUE NOT NULL,
    teacher_id  INTEGER           NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 老师邀请码（admin 发放，一码一用）
CREATE TABLE teacher_invite_codes
(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            VARCHAR(12) UNIQUE NOT NULL,
    status          VARCHAR(10) DEFAULT 'unused', -- unused/used/expired/revoked
    created_by      INTEGER            NOT NULL,
    used_by_user_id INTEGER,
    expire_at       DATETIME,
    created_at      DATETIME    DEFAULT CURRENT_TIMESTAMP,
    used_at         DATETIME
);

-- 作业
CREATE TABLE homework
(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER      NOT NULL,
    teacher_id  INTEGER      NOT NULL,
    title       VARCHAR(100) NOT NULL,
    description TEXT,
    subject     VARCHAR(20),
    deadline    DATETIME     NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 作业记录
CREATE TABLE homework_records
(
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    homework_id      INTEGER NOT NULL,
    student_id       INTEGER NOT NULL,
    start_time       DATETIME,
    submit_time      DATETIME,
    duration_minutes INTEGER,
    status           VARCHAR(10), -- not_started/doing/submitted/late
    file_url         VARCHAR(255),
    text_content     TEXT,
    points           INTEGER DEFAULT 0, -- 提交积分，不含批改积分
    review_score     INTEGER,           -- 0–100，NULL 表示未批改
    review_comment   TEXT,
    reviewed_at      DATETIME,
    reviewed_by      INTEGER,           -- 逻辑关联 users.id，不创建物理外键
    review_points    INTEGER NOT NULL DEFAULT 0, -- 批改积分实际净变动累计
    review_target_points INTEGER,                -- 上次批改目标档位积分，未批改为 NULL
    UNIQUE (homework_id, student_id)
);

-- 作业批改档位（admin 管理，独立于 point_rules）
CREATE TABLE homework_review_rules
(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    min_score  INTEGER NOT NULL UNIQUE,
    points     INTEGER NOT NULL DEFAULT 0,
    enabled    BOOLEAN NOT NULL DEFAULT 1,
    updated_by INTEGER, -- 逻辑关联 users.id，不创建物理外键
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 签到
CREATE TABLE checkins
(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL,
    checkin_date DATE    NOT NULL,
    points       INTEGER,
    streak       INTEGER,
    UNIQUE (student_id, checkin_date)
);

-- 文章
CREATE TABLE articles
(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id    INTEGER      NOT NULL,
    created_role VARCHAR(10),                     -- teacher/admin
    title        VARCHAR(100) NOT NULL,
    cover        VARCHAR(255),
    content      TEXT         NOT NULL,
    file_url     VARCHAR(255),                    -- 原始上传文件路径（迭代 v2.1）
    file_name    VARCHAR(255),                    -- 原始文件名（迭代 v2.1）
    file_type    VARCHAR(20),                     -- 原始文件类型 pdf/docx（迭代 v2.1）
    status       VARCHAR(10) DEFAULT 'published', -- published/hidden
    created_at   DATETIME    DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME
);

-- 阅读记录
CREATE TABLE reading_records
(
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id       INTEGER NOT NULL,
    student_id       INTEGER NOT NULL,
    duration_seconds INTEGER DEFAULT 0,
    finished         BOOLEAN DEFAULT 0,
    points           INTEGER DEFAULT 0,
    read_date        DATE,
    UNIQUE (article_id, student_id, read_date)
);

-- 游戏记录
CREATE TABLE game_records
(
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL,
    game_type        VARCHAR(20), -- sudoku/idiom
    difficulty       VARCHAR(10),
    score            INTEGER,
    points           INTEGER,
    duration_seconds INTEGER,
    play_date        DATE,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 积分流水（核心）
CREATE TABLE point_logs
(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER     NOT NULL,
    type        VARCHAR(20) NOT NULL, -- checkin/homework/reading/game/consume/review/parent_reward
    points      INTEGER     NOT NULL,
    remark      VARCHAR(255),
    operator_id INTEGER,
    log_date    DATE        NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 家长-学生关系
CREATE TABLE parent_students
(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id  INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    UNIQUE (parent_id, student_id)
);

-- 积分规则（admin 可改，动态生效）
CREATE TABLE point_rules
(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key     VARCHAR(50) UNIQUE NOT NULL,
    rule_name    VARCHAR(50)        NOT NULL,
    points       INTEGER            NOT NULL,
    daily_limit  INTEGER,
    extra_config TEXT, -- JSON
    enabled      BOOLEAN  DEFAULT 1,
    updated_by   INTEGER,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 管理员操作审计
CREATE TABLE admin_logs
(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER     NOT NULL,
    action      VARCHAR(50) NOT NULL,
    target_type VARCHAR(30),
    target_id   INTEGER,
    detail      TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 成语接龙题库（决策 4：admin 后台导入，不内置）
CREATE TABLE idiom_questions
(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt      VARCHAR(50) NOT NULL, -- 题干（上一个成语的末字/题目文本）
    answer      VARCHAR(50) NOT NULL, -- 正确答案
    distractors TEXT,                 -- JSON 数组，干扰项
    difficulty  VARCHAR(10) DEFAULT 'normal',
    enabled     BOOLEAN     DEFAULT 1,
    created_by  INTEGER,
    created_at  DATETIME    DEFAULT CURRENT_TIMESTAMP
);
```

**索引**：`point_logs(student_id, log_date)`、`homework_records(student_id)`、`users(class_id)`、
`teacher_invite_codes(code/status)`、`point_rules(rule_key)`、`idiom_questions(enabled)`

> **迁移**：本仓库无 Alembic，`create_all()` 只建缺失的表、**不修改已有表结构**。
> 新增列由 `python -m app.seed.migrate_v21` 显式 `ALTER`（幂等，可重复执行）。

### 4.2 积分规则种子数据

| rule_key           | rule_name | points | daily_limit | extra_config                  |
|--------------------|-----------|--------|-------------|-------------------------------|
| checkin_daily      | 每日签到      | 5      | 1           | —                             |
| checkin_streak_7   | 连续签到7天    | 10     | 1           | —                             |
| homework_on_time   | 作业按时提交    | 10     | NULL        | —                             |
| homework_late      | 作业迟交      | 5      | NULL        | —                             |
| reading_per_minute | 阅读每分钟     | 1      | 30          | `{"single_article_limit":10}` |
| reading_finish     | 读完文章      | 5      | NULL        | —                             |
| game_sudoku_easy   | 数独-简单     | 5      | 20          | —                             |
| game_sudoku_medium | 数独-中等     | 10     | 20          | —                             |
| game_sudoku_hard   | 数独-困难     | 15     | 20          | —                             |
| game_idiom         | 成语接龙每题    | 1      | 20          | —                             |

> 常规积分发放读取 `point_rules`，修改后立即生效；规则禁用则不发放。作业批改积分按下方独立档位表计算。

**作业批改档位种子**（表 `homework_review_rules`，PRD 5.3）

| min_score | points | 说明 |
|-----------|--------|------|
| 90 | 5 | 优秀 |
| 80 | 3 | 良好 |
| 60 | 1 | 合格 |

> 与 `point_rules` 分工不同：`point_rules` 是「一次行为发多少分」的单值规则，
> 本表是「分数区间 → 积分」的档位映射，admin 可在积分规则页增改启停。
> 匹配规则：取所有 `enabled` 且 `min_score <= score` 的档位中 `min_score` **最大**的一档；
> 无匹配则发 0 积分（不报错）。档位表为空会导致批改**静默**发 0 分，
> 故随 `initial_data` 与 `export_ddl` 一同初始化。

---

## 5. 功能需求

### 5.1 登录与认证

**注册**

- 用户名：**手机号**（`^1[3-9]\d{9}$`，校验格式与唯一性）
- 老师：用户名+密码+角色+**老师邀请码**（必填，校验存在/未用/未过期，**一码一用**）
- 学生：用户名+密码+角色+**班级邀请码**（必填，校验存在）→ 注册后自动加入班级
  - 班级邀请码**多学生可用**（班级属性，非一次性）；老师 / admin 可重新生成，旧码立即失效，已入班学生不受影响
- 家长：用户名+密码+角色+**学生绑定码**（必填，校验存在）→ 注册后自动绑定学生
  - 学生绑定码**多家长可用**（学生属性）；admin / 老师可重新生成，旧码立即失效，已建立的家长关系不受影响
- admin：不开放注册，种子初始化（`ADMIN_INIT_PASSWORD` 环境变量，缺省随机打印日志）

**登录**

- 用户名+密码 → JWT（含 user_id、role）
- admin 首次登录返回 `must_change_password: true`，未改密前其他接口 403
- 被禁用用户登录返回 403
- 登录之后可以自助修改当前账户密码 ✅（服务端契约已满足；Web 端右上角菜单 / 学生端「我的」页，小程序端四角色「我的」页）

**规则**

- 用户名唯一，3~20 位；密码 ≥6 位
- JWT 有效期 7 天，前端 localStorage

**接口**

```
POST /auth/register        {username, password, role, nickname, teacher_invite_code?, class_invite_code?, bind_code?}
POST /auth/login           {username, password} → {token, user, must_change_password?}
POST /auth/me              {}
POST /auth/change-password {old_password, new_password}
```

---

### 5.2 班级管理

- 老师创建班级（名称），生成 6 位邀请码
- 学生凭邀请码加入（一个学生只属一个班级）
- 老师查看班级学生、移除学生
- admin/老师 可看班级邀请码，且可以重新生成班级邀请码
- 学生端可查看绑定码
- admin/老师可重新生成学生绑定码

> **码的复用语义（v2.1 澄清）**
> - **班级邀请码**：班级属性，**多学生可用**，注册时校验存在即入班，不消耗、不失效；
>   老师 / admin 可重新生成，**旧码立即失效**，已加入该班的学生**不受影响**。
> - **学生绑定码**：学生属性，**多家长可用**，注册时校验存在即绑定，不消耗、不失效；
>   admin / 老师可重新生成，**旧码立即失效**，已建立的家长关系**不受影响**。
> - **老师邀请码**：**一码一用**，注册时消耗（`status=used`），此规则不变。

```
POST /classes/create             {name}                          teacher
POST /classes/join               {invite_code}                   student
POST /classes/my                 {}                              teacher/student
POST /classes/students           {class_id}                      teacher
POST /classes/remove-student     {class_id, student_id}          teacher
POST /classes/regenerate-invite   {class_id}                     teacher(admin 任意班级)
POST /classes/regenerate-bind-code {student_id}                  teacher(admin 任意学生)
```

---

### 5.3 老师端 — 作业管理

- 布置作业：标题、描述、科目、截止时间
- 查看作业列表与完成情况（学生、状态、开始时间、提交时间、用时、积分）
- 删除作业（仅无人提交时）
- 批改作业：打分（0–100）+ 评语，学生端可见
- 待批改清单：跨作业汇总已提交但未批改的记录

**时间采集**

- 「开始写作业」记录 `start_time`，重复点击不覆盖
- 「提交作业」记录 `submit_time`，`duration = submit - start`
- 超截止时间标记 `late`
- 用时 <1 分钟标记待审核（异常）

**批改与积分**

- 分数按「作业批改档位」表（`homework_review_rules`，分数下限 → 积分）换算为**额外积分**，admin 可配档位
- 匹配规则：取所有 `enabled` 且 `min_score <= score` 的档位中 `min_score` **最大**的一档；无匹配则发 0 积分（不报错）
- 首次批改的旧目标为 0；改分时按**新分数匹配的目标档位积分 − 上次批改保存的目标档位积分**补发/回扣，并保存新目标。档位规则变动不改写已保存的目标。
- 分数不变（包括单改评语）时不重新匹配档位、不调整积分，即使规则已变更也保留上次目标。
- 学生余额不足时**扣到 0 为止、未扣足部分永久豁免**；流水记实际扣减额。`review_points` 是实际批改积分净变动累计，可能不同于目标快照，也可能为负。
- 批改积分记 `point_logs.type='review'`，与提交时自动发放的 `homework` 类型隔离
- 只有**已提交**的作业可批改；未提交返回 400「学生尚未提交」
- 批改并发控制：批改时对 `homework_records` 行与 `users` 行加锁（`SELECT ... FOR UPDATE`），锁序固定为 `homework_records → users`，避免同一份作业重复发分与同一学生并发批改时余额互相覆盖
- 存量 MySQL 升级：先备份数据库，在停止业务写入并确认数据库连接后运行 `python -m app.seed.migrate_homework_review --check` 查看待执行项，再运行 `python -m app.seed.migrate_homework_review`；`create_all()` 不会为已有表增加字段。
  - 若 `homework_review_rules` 不存在，迁移在本次调用中建表并写入默认档位种子；若表已存在且非空，绝不覆盖已有规则。
  - 若表已存在但为空，无法判断是管理员有意清空还是迁移中断所致，必须故障关闭：包括 `--check` 在内均报错停止，不自动写入种子。先检查备份并确认管理员意图，再由管理员手动恢复预期规则，之后重新检查并迁移。
  - 已批改但缺少目标快照的记录按迁移时当前启用档位匹配初始化，无匹配记 0；不改变余额、实际净变动或流水。历史规则不可还原，因此此基线不一定等于当年的目标；重复执行不覆盖快照。
  - MySQL DDL 会隐式提交，迁移并非原子操作；中断后应检查实际状态。若建表已提交但种子未写入，重跑会遇到已有空表并停止，须先按上述流程人工恢复规则，再重跑迁移；其他中断也可能需要人工恢复。

```
POST /homework/create   {class_id, title, description, subject, deadline}  teacher
POST /homework/list     {class_id, page, size}                             teacher
POST /homework/today    {}                                                 student
POST /homework/my-list  {page?, size?}                                     student
POST /homework/detail   {homework_id}                                      all
POST /homework/records  {homework_id}                                      teacher
POST /homework/delete   {homework_id}                                      teacher
POST /homework/start    {homework_id}                                      student
POST /homework/submit   multipart: homework_id, text_content, file?        student
POST /homework/review   {homework_id, student_id, score, comment?}          teacher
POST /homework/pending  {page, size}                                       teacher
```

`/homework/my-list` 仅学生可用，仅查询当前班级中该学生本人 `submit_time` 非空的记录（包含迟交），不包含已转出班级的作业。`page` 默认 1 且 ≥1，`size` 默认 20、范围 1–100。按 `submit_time` 倒序，时间相同时按作业记录 `id` 倒序稳定分页；数据发生变化时分页结果可能变化。无班级返回空分页。响应 `data` 为 `{list, total, page, size}`；列表每项含今日列表的作业字段 `id, class_id, teacher_id, title, description, subject, deadline, created_at, my_status, my_points`，以及 `my_record`，包含记录 `id, homework_id, student_id, start_time, submit_time, duration_minutes, status, file_url, text_content, points, suspicious, review_score, review_comment, reviewed_at, review_points`。时间为 ISO 8601 字符串，未批改字段可为 null。

`/homework/review` 响应 `data` 含 `record`（含批改字段）、`points_delta`（目标差额：正=应补发，负=应回扣）、`awarded_points`（实际净变动：正=实发，负=实扣；余额不足时其绝对值小于 `|points_delta|`）。

---

### 5.4 学生端 — 签到 / 排行榜

**签到**

- 每日 1 次 +5；连续 7 天额外 +10
- 当天已签到返回状态

**排行榜**

- 今日榜：按当日 PointLog 聚合，前 50
- 总榜：按 total_points，前 50
- 同分按达成时间先后
- 返回 `my_rank`（不在前 50 也可见自己排名）
- **排除 admin 角色**

```
POST /checkin/do      {}   student
POST /checkin/status  {}   student
POST /points/rank     {type: "day"|"total", page, size}   admin/teacher/student
POST /points/log      {page, size, type?}                 student
POST /points/summary  {}                                  student
```

---

### 5.5 课后阅读

**发布**：老师/ **admin** 均可发布（`created_role` 区分）
**阅读计时与防挂机**

- 进入页面计时，失焦暂停
- 每 30 秒心跳上报，后端校验间隔 30s±10s，异常不计时
- 滚动到底标记读完
- 阅读文章支持导出 PDF 文件
- 发布阅读文章支持纯文本/PDF/word文档
- 阅读时只读，不可编辑

**发布与导出（v2.1）**

- 发布支持纯文本 / PDF / word 文档：上传文件由服务端抽取正文入库（原文件保留，
  `articles.file_url` / `file_name` / `file_type`），学生端读到的仍是**文本**（天然只读）
- 阅读文章支持导出 PDF：服务端用 reportlab 排版（内置中文 CID 字体 `STSong-Light`，
  无需外部字体文件），生成的 PDF 存 `uploads/` 并返回可下载地址
- 阅读时只读，不可编辑（学生端无任何编辑入口）
- 上传与导出的文件通过 `GET /homework_api/uploads/<name>` 访问（静态挂载，非业务接口；`file_url` 仍为相对 API 基址的 `/uploads/<name>`）

**积分**（读规则表）

- 每分钟 +1，单篇上限 10，日上限 30
- 读完 +5，单篇 1 次

```
POST /articles/create     {title, cover, content}          teacher/admin
POST /articles/create-file multipart: title, cover?, content?, file?   teacher/admin
POST /articles/list       {page, size}                     all（仅 published）
POST /articles/detail     {article_id}                     all
POST /articles/heartbeat  {article_id, seconds}            student
POST /articles/finish     {article_id}                     student
POST /articles/records    {article_id}                     teacher
POST /articles/delete     {article_id}                     teacher（仅自己）
POST /articles/export-pdf {article_id}                     all（学生仅 published）
```

---

### 5.6 课后小游戏

**数独**：难度分级，计时，完成提交按难度给分（规则表）

- 题库由**服务端内置生成算法**按难度实时生成，无需预置题库
- 数独游戏，增加游戏规则说明

**成语接龙**：60 秒限时闯关，答对 +1/题

- 题库由 **admin 后台导入**至 `idiom_questions` 表（决策 4），不内置于代码
- 导入接口见 5.8.6

**防沉迷**：每日游戏总积分上限 20（规则表 daily_limit）

```
POST /games/sudoku/start   {difficulty}                  student
POST /games/sudoku/result  {puzzle_id, duration, success} student
POST /games/idiom/start    {}                            student
POST /games/idiom/question {}                            student
POST /games/idiom/answer   {session_id, answer}          student
POST /games/idiom/result   {session_id}                  student
POST /games/records        {page, size}                  student
```

---

### 5.7 家长端 — 积分消耗与奖励

- 学生生成绑定码，家长输入绑定（可绑多个）
- 查看孩子积分与明细
- 查看排行榜：仅家长可查询已绑定的学生；返回与 `/points/rank` 相同的榜单，`my_rank` 为指定孩子的名次
- 消耗：预设事项（看手机-5、看电视-5、买玩具-20、买零食-10、自定义）
- 校验余额 ≥ 扣分，否则 400
- 写 PointLog（type=consume，points 为负，operator=家长）
- 奖励：预设主动承担家务 5 分、积极完成作业 5 分、不挑食 3 分，也可自定义事项及分值；预设仅供参考，不限制提交内容
- 奖励仅限已绑定孩子；`points` 为 1–10000 的整数，`item` 为 1–50 字符，`remark` 可省略或为 null、最多 204 字符；流水备注为事项与非空备注以 `：` 拼接，拼接后最多 255 字符，超出返回 400
- 奖励不读取积分规则、不设每日上限；事务中锁定学生和绑定关系，写正数流水 `type=parent_reward`、`operator_id=家长 ID` 并同步增加余额，计入今日及累计获得统计
- 奖励成功返回统一响应 `data={student_id, item, points, total_points}`；预设接口返回 `data={list: [{key, name, points}, ...]}`。非家长或未绑定返回 403，学生不存在返回 404，参数校验失败返回 400

```
POST /parent/bind          {bind_code}                    parent
POST /parent/children      {}                             parent
POST /parent/child-points  {student_id, page, size}       parent
POST /parent/child-rank    {student_id, type, page, size} parent
POST /parent/consume       {student_id, item, points, remark} parent
POST /parent/reward        {student_id, item, points, remark?} parent
POST /parent/reward-items  {}                             parent
POST /parent/consume-items {}                             parent
POST /parent/unbind        {student_id}                   parent
```

`/parent/child-rank` 的 `student_id` 必填；`type` 默认 `day`，可选 `day` 或 `total`；`page` 默认 1 且 ≥1，`size` 默认 50、范围 1–50。响应 `data` 为 `{type, list, total, page, size, my_rank}`，`list` 每项含 `{rank, user_id, username, nickname, points}`，其中 `username` 固定为 null，避免向家长暴露其他学生的账号；`my_rank` 为孩子在完整榜单中的名次，未上榜为 0。榜单范围、排序和分页与 `/points/rank` 一致。非家长、未绑定或绑定用户不是学生返回 403，学生不存在返回 404，参数校验失败返回 400；身份与绑定关系由服务端验证。

---

### 5.8 超级管理员（admin）

#### 5.8.1 老师邀请码管理

- 批量生成（1~50 个），有效期默认 7 天
- 列表（状态筛选）、撤销未使用码
- 一码一用，使用后记录使用者与时间

```
POST /admin/invite/create  {count, expire_days} → {codes: []}
POST /admin/invite/list    {status?, page, size}
POST /admin/invite/revoke  {code_id}
```

#### 5.8.2 用户管理（全角色启用/禁用）

- 查看全部用户（角色/状态筛选、搜索）
- **禁用/启用 teacher/student/parent**
- **不可操作 admin（含自己）**，返回 400
- 重置密码（生成临时密码，强制改密）
- 禁用立即生效（JWT 依赖查库校验 status）

```
POST /admin/users/list           {role?, status?, keyword?, page, size}
POST /admin/users/disable        {user_id}
POST /admin/users/enable         {user_id}
POST /admin/users/reset-password {user_id} → {temp_password}
POST /admin/users/detail         {user_id}
```

#### 5.8.3 积分规则管理

- 查看全部规则（key、名称、积分、日上限、扩展配置、启用、更新时间）
- 编辑：积分值、日上限、扩展配置 JSON、启用/禁用
- 修改立即生效（规则服务缓存失效），写 `admin_logs`
- `rule_key` 不可改

```
POST /admin/rules/list         {}
POST /admin/rules/detail       {rule_key}
POST /admin/rules/update       {rule_key, points, daily_limit, extra_config, enabled}
POST /admin/rules/batch-update {rules: [{rule_key, points, ...}]}
```

**作业批改档位**（PRD 5.3，档位区间映射，独立于 `point_rules`）

```
POST /admin/homework-review-rules/list    {}
POST /admin/homework-review-rules/create  {min_score, points}
POST /admin/homework-review-rules/update  {id, points?, enabled?}
```

#### 5.8.4 文章管理（全量）

- 查看全部文章（按作者角色/作者/状态/关键词筛选）
- 编辑、上下架（published/hidden）、删除
- 查看阅读统计（阅读人数、完成数、总时长）
- 学生端仅见 `published`

```
POST /admin/articles/list    {author_role?, author_id?, status?, keyword?, page, size}
POST /admin/articles/detail  {article_id} → {article, stats}
POST /admin/articles/update  {article_id, title, cover, content}
POST /admin/articles/toggle  {article_id, status}
POST /admin/articles/delete  {article_id}
POST /admin/articles/stats   {article_id}
```

#### 5.8.5 班级与全局统计

```
POST /admin/classes/list    {page, size}
POST /admin/stats/overview  {} → {user_count, class_count, homework_count, point_total, ...}
```

#### 5.8.6 成语题库管理（决策 4）

- 批量导入题目（支持 JSON 文件或逐条提交，单次上限 1000 条）
- 导入校验：`prompt`/`answer` 非空；同批内 `prompt` 去重；已存在则跳过或覆盖（由参数 `mode` 决定：`skip`/`overwrite`）
- 干扰项 `distractors` 为 JSON 数组，建议 ≥2 个；不足时服务端随机补齐
- 列表支持关键词、启用状态筛选、分页
- 单条编辑 / 删除 / 批量删除；写 `admin_logs`
- 题目 `enabled=false` 后学生端不再抽到

```
POST /admin/idioms/import     {items: [{prompt, answer, distractors?, difficulty?}], mode?} → {success_count, skipped_count}
POST /admin/idioms/list       {keyword?, enabled?, page, size}
POST /admin/idioms/update     {question_id, prompt, answer, distractors, difficulty, enabled}
POST /admin/idioms/delete     {question_id}
POST /admin/idioms/batch-delete {question_ids: []}
```

---

## 6. 积分规则总表（可由 admin 动态修改）

| 行为          | rule_key           | 默认积分       | 日上限      |
|-------------|--------------------|------------|----------|
| 每日签到        | checkin_daily      | +5         | 1 次      |
| 连续签到7天      | checkin_streak_7   | +10        | 1 次      |
| 作业按时提交      | homework_on_time   | +10        | —        |
| 作业迟交        | homework_late      | +5         | —        |
| 阅读每分钟       | reading_per_minute | +1         | 30（单篇10） |
| 读完文章        | reading_finish     | +5         | —        |
| 数独 简单/中等/困难 | game_sudoku_*      | +5/+10/+15 | 游戏合计20   |
| 成语接龙每题      | game_idiom         | +1         | 游戏合计20   |
| 家长扣分        | —（不走规则表）           | -N         | 余额≥0     |

**通用**

- 积分变动必写 `point_logs`，同步 `users.total_points`
- 日上限服务端强校验
- `total_points` 不为负
- 规则 `enabled=false` 不发放

---

## 7. 接口清单（全 POST 总览）

本节路径均相对于含 `/homework_api` 的 API 基址；实际请求路径须加此前缀，详见 3.1 节。清单包含尚未实现的契约，不能仅凭列出判断已实现。

```
# 认证
POST /auth/register
POST /auth/login
POST /auth/me
POST /auth/change-password

# 班级
POST /classes/create
POST /classes/join
POST /classes/my
POST /classes/students
POST /classes/remove-student
POST /classes/regenerate-invite
POST /classes/regenerate-bind-code

# 作业
POST /homework/create
POST /homework/list
POST /homework/today
POST /homework/my-list
POST /homework/detail
POST /homework/records
POST /homework/delete
POST /homework/start
POST /homework/submit
POST /homework/review
POST /homework/pending

# 签到
POST /checkin/do
POST /checkin/status

# 积分
POST /points/rank
POST /points/log
POST /points/summary

# 阅读
POST /articles/create
POST /articles/create-file
POST /articles/list
POST /articles/detail
POST /articles/heartbeat
POST /articles/finish
POST /articles/records
POST /articles/delete
POST /articles/export-pdf

# 游戏
POST /games/sudoku/start
POST /games/sudoku/result
POST /games/idiom/start
POST /games/idiom/question
POST /games/idiom/answer
POST /games/idiom/result
POST /games/records

# 家长
POST /parent/bind
POST /parent/children
POST /parent/child-points
POST /parent/child-rank
POST /parent/consume
POST /parent/reward
POST /parent/reward-items
POST /parent/consume-items
POST /parent/unbind

# 超级管理员
POST /admin/invite/create
POST /admin/invite/list
POST /admin/invite/revoke
POST /admin/users/list
POST /admin/users/disable
POST /admin/users/enable
POST /admin/users/reset-password
POST /admin/users/detail
POST /admin/rules/list
POST /admin/rules/detail
POST /admin/rules/update
POST /admin/rules/batch-update
POST /admin/homework-review-rules/list
POST /admin/homework-review-rules/create
POST /admin/homework-review-rules/update
POST /admin/idioms/import
POST /admin/idioms/list
POST /admin/idioms/update
POST /admin/idioms/delete
POST /admin/idioms/batch-delete
POST /admin/articles/list
POST /admin/articles/detail
POST /admin/articles/update
POST /admin/articles/toggle
POST /admin/articles/delete
POST /admin/articles/stats
POST /admin/classes/list
POST /admin/stats/overview

# 健康检查
POST /health
```

---

## 8. 权限矩阵

| 功能                           | admin | teacher | student | parent  |
|------------------------------|-------|---------|---------|---------|
| 生成/撤销老师邀请码                   | ✅     | ❌       | ❌       | ❌       |
| 禁用/启用 teacher/student/parent | ✅     | ❌       | ❌       | ❌       |
| 禁用/启用 admin                  | ❌     | ❌       | ❌       | ❌       |
| 重置用户密码                       | ✅     | ❌       | ❌       | ❌       |
| 修改积分规则                       | ✅     | ❌       | ❌       | ❌       |
| 发布文章                         | ✅     | ✅       | ❌       | ❌       |
| 管理全部文章                       | ✅     | ❌       | ❌       | ❌       |
| 管理自己文章                       | —     | ✅       | ❌       | ❌       |
| 查看全局统计                       | ✅     | ❌       | ❌       | ❌       |
| 创建班级                         | ❌     | ✅       | ❌       | ❌       |
| 加入班级                         | ❌     | ❌       | ✅       | ❌       |
| 布置作业/看完成情况                   | ❌     | ✅（自己班级） | ❌       | ❌       |
| 签到/交作业/阅读/游戏                 | ❌     | ❌       | ✅       | ❌       |
| 查看排行榜                        | 只读    | 只读      | 只读      | 只读（通过绑定孩子） |
| 积分消耗                         | ❌     | ❌       | ❌       | ✅（绑定孩子） |
| 重新生成班级邀请码                  | ✅     | ✅（自己班级） | ❌       | ❌       |
| 重新生成学生绑定码                  | ✅     | ✅（本班学生） | ❌       | ❌       |
| 发布文章（纯文本/PDF/word）         | ✅     | ✅       | ❌       | ❌       |
| 导出文章 PDF                      | ✅     | ✅       | ✅      | ❌       |

> admin 不参与业务（不签到、不布置作业），不计入排行榜。

---

## 9. 前端页面清单

**四角色 × 两平台全覆盖**（决策 2 修订）：学生 / 家长 / 老师 / admin
在**小程序端与 Web 端（zg-tsp-web）均提供**。

> 小程序端一期覆盖学生端与家长端，老师端与 admin 端排在二期
> （阶段性偏离，见 [小程序.md](小程序.md) §1.1）。

差异仅在**交互形态**，不在**功能覆盖**：

| 维度         | 小程序端                         | Web 端                       |
|------------|------------------------------|----------------------------|
| 布局          | 移动优先，单列/卡片                     | 桌面优先，表格/抽屉/多列               |
| 复杂表格        | 简表 + 详情页                        | 完整表格、排序、筛选、批量编辑           |
| 富文本编辑      | 简化编辑器                           | 完整富文本编辑器                  |
| 文件上传        | 相册 / 文件选择                     | 拖拽上传 + 文件选择            |
| 批量操作       | 逐条操作                             | 多选批量（如成语题库批量导入）             |

> 任何功能不得仅存在于单一平台；若某功能在某平台形态受限，
> 需提供等效入口（如小程序端「批量删除成语题目」→ 逐条删除）。

### 9.1 公共页面（小程序端 + Web 端均提供）

- 登录页 / 注册页（选角色 student / parent / teacher；选 teacher 显示邀请码输入）
- admin 首次登录强制改密页
- 我的（个人资料、改密）

### 9.2 学生端（小程序端 + Web 端均提供）

- 首页：签到、今日积分、今日作业、排行榜入口
- 作业列表 / 详情（开始写作业、上传提交）
- 阅读列表 / 详情（计时、心跳、读完标记、导出 PDF、只读）
- 游戏中心 / 数独 / 成语接龙
- 排行榜（日榜 / 总榜）
- 我的积分明细
- 我的（查看**绑定码**、所属班级、改密入口）
- 首次使用：加入班级页

### 9.3 家长端（小程序端 + Web 端均提供）

- 孩子列表 / 绑定
- 孩子积分与明细
- 积分消耗（预设事项 + 自定义）

### 9.4 老师端（小程序端 + Web 端均提供）

- 我的班级 / 班级学生列表（可重新生成班级邀请码 / 学生绑定码）
- 布置作业
- 作业完成情况（学生、状态、开始时间、提交时间、用时、积分）
- 文章管理 / 发布（纯文本 / PDF / word）/ 阅读记录 / 导出 PDF
- 班级积分概览

### 9.5 admin 端（小程序端 + Web 端均提供）

- 邀请码管理（生成 / 列表 / 复制 / 撤销）
- 用户管理（全角色筛选、禁用 / 启用、重置密码；admin 行按钮置灰）
- 积分规则管理（积分值、日上限、扩展配置 JSON、启用开关）
- 文章管理（全量列表、编辑、上下架、删除、阅读统计）
- 发布文章（纯文本 / PDF / word）、导出 PDF
- 成语题库管理（批量导入 JSON / 文件、列表、编辑、启用开关、删除）
- 班级总览
- 数据概览（统计卡片）

### 9.6 平台实现分工

| 功能点           | 小程序端                | zg-tsp-web |
|----------------|---------------------|-----------|
| 四角色登录 / 注册   | ✅（一期）               | ✅         |
| 学生端全部功能     | ✅（一期）               | ✅         |
| 家长端全部功能     | ✅（一期）               | ✅         |
| 老师端全部功能     | ⬜ 二期（手机形态）         | ✅（桌面形态）   |
| admin 端全部功能   | ⬜ 二期（手机形态）         | ✅（桌面形态）   |
| 成语题库批量导入    | 逐条导入（二期）            | 批量导入      |

> 小程序端为**独立仓库**（决策 6），位于本聚合检出之外，功能范围与排期见
> [小程序.md](小程序.md)。老师端与 admin 端排在二期，属本节的阶段性偏离。
- 班级总览
- 数据概览（统计卡片）

---

## 10. 非功能性需求

### 10.1 安全

- 全 POST + Body，URL 无业务参数
- 密码 bcrypt，JWT 校验 role + status
- 禁用用户立即失效（查库）
- admin 保护：用户操作接口先校验目标非 admin
- 邀请码 12 位随机，注册限流 10 次/分钟/IP
- 文件白名单：作业 jpg/png/pdf ≤10MB；文章 pdf/docx ≤10MB（v2.1）
- 敏感操作写 `admin_logs`

### 10.2 防刷

- 每日积分上限服务端强制
- 阅读心跳间隔校验
- 作业用时 <1 分钟标记异常
- 签到/提交类接口限流 10 次/分钟/用户

### 10.3 性能

- 排行榜查询走索引，结果缓存 60s（可选）
- 积分规则服务缓存 60s，update 失效
- 小程序端适配（学生/家长），桌面优化（老师/admin）

### 10.4 初始化

- 启动种子：若无 admin 则创建（用户名 `admin`，密码取 `ADMIN_INIT_PASSWORD`，缺省随机打印日志）
- 启动种子：`point_rules` 默认规则（已存在则跳过）
- admin 首登强制改密

---

## 11. 开发计划

| Phase | 模块            | 内容                                                                      |
|-------|---------------|-------------------------------------------------------------------------|
| P0    | 三模块骨架         | 建立三模块目录与工程初始化；各模块依赖清单、配置外置（`.env.example`）、独立启动脚本、Dockerfile；确保无跨模块源码依赖 |
| P1    | zg-tsp-server | 建表、种子（admin+规则）、JWT 认证、注册登录（老师邀请码校验）                                    |
| P1.5  | zg-tsp-server | admin 基础：邀请码管理、用户管理（全角色禁用/启用）、全局统计                                      |
| P1.6  | zg-tsp-server | 积分规则管理：规则服务+缓存、admin CRUD、各积分点接入                                        |
| P2    | zg-tsp-server | 班级、作业布置、开始/提交打点                                                         |
| P3    | zg-tsp-server | 签到、PointLog、日榜/总榜、积分明细（读规则表）                                            |
| P4    | zg-tsp-server | 家长绑定与扣分                                                                 |
| P5    | zg-tsp-server | 阅读：文章发布（teacher/admin）、计时防挂机、阅读积分、admin 文章管理                            |
| P6    | zg-tsp-server | 游戏：数独、成语接龙、游戏积分与上限                                                      |
| P7    | zg-tsp-web    | **四角色**页面：学生 / 家长 / 老师 / admin（P1.5 起可并行开工）                            |
| P8    | 小程序端        | **四角色**页面：学生 / 家长 / 老师 / admin（独立仓库，一期学生 + 家长）                  |
| P9    | 全模块           | 联调、权限校验、防刷、适配、验收                                                        |

> 服务端 P1~P6 为关键路径，Web / 小程序端在对应接口就绪后并行推进。
> 小程序端与 Web 端均为**四角色全覆盖**（第 9 节），差异仅在交互形态，无功能缺口。

**LLM 开发指令**：先输出「项目结构 + 建表 SQL + 种子 + 认证模块」并确认，再按 Phase 逐模块生成，每阶段可运行测试。

---

## 12. 验收标准

- [ ] 四角色可登录，权限隔离正确；admin 不出现在排行榜、不参与业务
- [ ] 老师注册必须携带有效邀请码，一码一用，无效/过期/已用拒绝
- [ ] admin 可批量生成/撤销邀请码
- [ ] admin 可禁用/启用 teacher/student/parent，禁用后立即无法登录与调用接口
- [ ] admin 无法禁用 admin（含自己），返回 400
- [ ] admin 可修改积分规则，修改后新发放立即按新值执行；禁用规则不发放
- [ ] admin 可发布/编辑/上下架/删除任意文章；老师仅能管自己的
- [ ] 学生可加入班级、老师可布置作业
- [ ] 学生开始/提交作业，老师能看到开始时间与用时
- [ ] 签到、作业、阅读、游戏积分正确且受日上限约束
- [ ] 日榜/总榜正确，自己排名可见
- [ ] 阅读切后台暂停计时，挂机不计分
- [ ] 家长可绑定孩子并扣分，余额不足拦截
- [ ] 所有积分变动可在明细追溯
- [ ] 敏感操作（禁用、规则修改、文章删除）有审计日志
- [ ] 学生/家长端小程序可用（按小程序.md 排期）
- [ ] 业务接口均为 POST，URL 不携带业务参数；静态文件和 API 文档使用 GET

**迭代 v2.1（注册 / 班级码 / 阅读文档能力）**

- [ ] 注册用户名必须是手机号，格式非法返回 400
- [ ] 学生注册携带班级邀请码后自动入班；家长注册携带学生绑定码后自动绑定
- [ ] 班级邀请码可被多个学生使用；学生绑定码可被多个家长使用
- [ ] admin / 老师可重新生成班级邀请码与学生绑定码，旧码立即失效且已有关系不受影响
- [ ] 学生端可查看自己的绑定码（Web 与小程序端均提供入口）
- [ ] 老师 / admin 可发布 PDF / word 文章，正文由服务端正确抽取
- [ ] 文章可导出为 PDF 且文件可正常打开
- [ ] 上传与导出的文件可通过 `/homework_api/uploads/<name>` 访问，返回的 `file_url` 仍为相对 API 基址的 `/uploads/<name>`

**模块独立性**

- [ ] 各模块均可单独检出、单独安装依赖、单独启动，互不依赖其他模块的构建产物
- [ ] 任一模块重新构建/发版，不触发也不破坏其他模块
- [ ] 任一模块的源码中不含对其他模块的 import / 路径引用 / 构建期依赖
- [ ] 服务端不可用时，Web 能正常启动并给出降级提示，不崩溃
- [ ] 服务端地址均为外部配置项，代码中无硬编码地址
- [ ] 各模块可独立版本化发布；服务端小版本升级不强制客户端同步发版
- [ ] 小程序端测试/生产环境可分别配置，API 基地址由配置项外置
- [ ] 小程序端各角色可完成核心操作（按小程序.md 排期验收）
- [ ] **四角色 × 两平台功能对齐**：任一功能在小程序端或 Web 端均不存在功能缺口
- [ ] 小程序端批量操作有逐条等效入口（成语题库导入/删除等）
- [ ] admin 可导入成语题库（≥200 条），导入去重与校验生效；禁用题目学生端抽不到
- [ ] 服务端 `POST /homework_api/health` 可用，未引入多余的监控依赖

---

## 13. 已确认的技术决策

以下事项已拍板，作为后续开发的既定前提：

| # | 事项       | 决策                                   | 影响                                         |
|---|----------|--------------------------------------|--------------------------------------------|
| 1 | 小程序端技术栈  | **微信原生小程序**（WXML/WXSS/JS，无构建链）      | 微信开发者工具构建，无 Gradle/Xcode 依赖；独立仓库，满足模块独立性 |
| 2 | 角色 × 平台覆盖  | **四角色 × 两平台全覆盖**：学生/家长/老师/admin 在小程序端与 Web 端均提供 | 两个客户端均为四角色全量功能，差异仅在交互形态，见第 9 节   |
| 3 | 多班级支持    | **不支持**，一个学生只属一个班级                   | `users.class_id` 单值，无需关联表                  |
| 4 | 成语接龙题库来源 | **后台导入**                             | 需新增 `idiom_questions` 表 + admin 导入接口 + 导入页 |
| 5 | 数独题库来源   | **内置生成算法**                           | 服务端按难度算法生成，无需预置题库                          |
| 6 | 仓库形态     | **独立仓库**，非 monorepo（小程序端为第四个仓库，在聚合检出外） | 各模块独立 clone/发版；本仓库仅作聚合与文档同步                |
| 7 | 环境渠道     | **测试 + 生产**（Web 两套构建变量，小程序端 dev/prod 配置）  | 见 2.2.2；地址均外置，不硬编码                         |
| 8 | 健康检查与监控  | **仅 `/homework_api/health`**，暂不引入就绪探针与 Prometheus | P0 仅需实现该健康检查                          |

### 13.1 决策衍生需求

- **决策 2 衍生**：小程序端与 Web 端均为**四角色全量功能**，差异仅在交互形态
  （小程序端简表/卡片，Web 端完整表格/抽屉/批量编辑）。
  **不得出现某功能仅存在于单一平台的情况**；小程序端缺失的批量操作需提供逐条等效入口。
- **决策 4 衍生**：新增数据表与接口（补充至第 4、7 节）：
    - `idiom_questions` 表（成语题库，含答案、难度）
    - `POST /admin/idioms/import`（批量导入）、`POST /admin/idioms/list`
    - `POST /games/idiom/question`（学生端取题）
- **决策 6 衍生**：各模块拆分独立仓库后，接口契约需有唯一权威来源；
  本文档（第 7 节接口清单）即为契约基线，各仓库以其为准。
- **决策 8 衍生**：不引入监控依赖，`/homework_api/health` 返回静态 `status`，不探测数据库连通性。

---

## 14. 补充需求：家长作业、文章与鉴权文件访问

本节为新增待实现需求及接口契约，不表示现有服务端已实现；与前文冲突时以本节为准，原有 `/uploads` 行为及其风险不因此消失。

- 家长可选择已绑定的孩子，查看该孩子**当前班级**的作业列表、详情及其提交和批改情况；无班级时列表为空，不得查看转出班级的作业。服务端对每次请求校验家长身份、当前绑定关系及孩子当前班级，拒绝越权访问。
- 家长可为已绑定孩子拍照并代为正式提交作业，提交到该孩子的正式作业记录，而非草稿；沿用学生提交的内容、附件、截止时间、迟交、重复提交、积分与批改等规则。不得代替孩子调用开始作业或伪造 `start_time`；已有真实开始时间时予以保留，无真实开始时间时保持为空，用时不得虚构。
- 家长可只读查看已发布文章及下载其 PDF；不发阅读心跳、不标记读完、不创建或修改孩子的阅读计时及积分记录。隐藏或下架文章不可通过家长接口查看或下载。
- 下列新增接口均为 `POST`，请求使用 `Authorization: Bearer <token>`；标识符放在 Body 中。普通业务接口返回统一 JSON 响应，文件下载成功返回对应文件的二进制流，失败返回统一错误响应。家长接口逐次校验身份及必要的数据访问权限；文件接口不得根据客户端提供的任意路径直接读取文件。

```
POST /parent/homework/list      {student_id, page?, size?}              parent，当前班级作业
POST /parent/homework/detail    {student_id, homework_id}               parent
POST /parent/homework/submit    multipart: student_id, homework_id, text_content?, file?  parent
POST /parent/homework/download  {student_id, homework_id}               parent，下载作业内容与作答 PDF，不含附件
POST /homework/attachment       {homework_id, student_id}                按调用者角色及作业记录权限鉴权，下载附件
POST /parent/articles/list      {student_id, page?, size?}              parent，仅已发布
POST /parent/articles/detail    {student_id, article_id}                parent，仅已发布
POST /parent/articles/download  {student_id, article_id}                parent，仅已发布，PDF 二进制流
```

- 本节家长流程的 PDF 和作业附件使用上述 Bearer 鉴权的 POST 二进制流，不通过公开 URL 下载；服务端在返回文件前校验资源状态及访问权限。原学生文章导出接口仍返回公开 URL，不能视为鉴权下载。
- **历史风险**：现存 `GET /homework_api/uploads/<name>` 静态挂载不鉴权，已公开的文件仍可被知晓有效地址者访问；新增鉴权接口并不撤销公开访问或自动保护已有文件，需另行治理存量文件与公开访问。旧地址能否继续访问取决于部署时是否保留映射。

**补充验收**

- [ ] 家长只能查看及提交已绑定孩子当前班级的作业；解绑、转班后旧权限不再生效，越权请求被拒绝。
- [ ] 代拍附件真实进入正式提交；按时/迟交、重复提交、积分及批改与学生提交规则一致；有真实开始时间则保留，无开始时间不伪造时间和用时。
- [ ] 家长只能查看、下载已发布文章，阅读及下载不产生阅读记录、计时或积分。
- [ ] PDF 和附件经 Bearer 鉴权 POST 返回二进制流；未认证、无权限及不可用资源不返回文件；历史 `/uploads` 公开链接风险已明确记录。

