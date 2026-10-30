# 学校兴趣培养积分系统 — 完整 PRD（v2.1）

> 版本：v2.1（迭代：手机号注册 / 班级码与绑定码重生成 / 阅读文档能力）  
> 技术栈：React + Ant Design 前端 / Python FastAPI 后端 / JWT 认证  
> 接口约定：**全部使用 POST，参数走 Body**，避免 URL 信息泄露  
> 文档目的：作为 LLM 直接开发项目的唯一依据

---

## 0. 变更记录

### v2.1（迭代：注册 / 班级码 / 阅读文档能力）

**来源**：`sys_doc/迭代.md`

| # | 变更项 | 说明 |
|---|--------|------|
| 1 | 注册用户名改为手机号 | 格式 `^1[3-9]\d{9}$`，并校验唯一性（PRD 5.1） |
| 2 | 学生注册带**班级邀请码** | 注册时校验班级邀请码存在，注册后**自动加入班级**。班级邀请码**多学生可用**（班级属性），老师 / admin 可重新生成，旧码立即失效，已入班学生不受影响 |
| 3 | 家长注册带**学生绑定码** | 注册时校验绑定码存在，注册后**自动绑定学生**。学生绑定码**多家长可用**（学生属性），admin / 老师可重新生成，旧码立即失效，已建立的家长关系不受影响 |
| 4 | 老师邀请码维持一码一用 | 注册时消耗，`status=used`（不变） |
| 5 | admin / 老师可重新生成班级邀请码 | 新增 `POST /classes/regenerate-invite` |
| 6 | admin / 老师可重新生成学生绑定码 | 新增 `POST /classes/regenerate-bind-code` |
| 7 | 学生端可查看绑定码 | 服务端 `/auth/me` 已返回 `bind_code`；Web 新增学生端「我的」页，移动端「我的」页已有 |
| 8 | 发布文章支持纯文本 / PDF / word | 新增 `POST /articles/create-file`（multipart），服务端抽取正文入库；`articles` 表新增 `file_url` / `file_name` / `file_type` |
| 9 | 阅读文章支持导出 PDF | 新增 `POST /articles/export-pdf`，服务端用 reportlab 排版（内置中文 CID 字体 `STSong-Light`） |
| 10 | 阅读时只读不可编辑 | 学生端无任何编辑入口，正文只读渲染（已在 Web / 移动端落实，并加只读标识） |
| 11 | 登录后可自助修改当前账户密码 | `POST /auth/change-password` 已实现；本迭代在 Web（右上角菜单 / 学生端「我的」页）与移动端补充入口 |
| 12 | 修复上传文件无法访问 | `app/main.py` 新增 `StaticFiles("/uploads")` 挂载（此前 `/uploads/<name>` 无对应路由，作业附件与导出文件实际 404） |

> **本版本未覆盖的既有缺口（非本次迭代范围，遗留待办）**
> - 5.8.4 列出的 `POST /admin/articles/{list,detail,update,toggle,stats}` 六个端点**服务端仍未实现**；
>   admin 端的文章管理当前走 `/articles/*` 既有路由 + 前端筛选。
> - 5.6 提出的「数独游戏规则说明」尚未在移动端数独页内呈现。

> **口径澄清**：`迭代.md` 中「班级邀请码 / 学生绑定码一码一用」与 PRD 5.2「一个班级多个学生加入」、5.7「家长可绑多个孩子」冲突。
> 本版本按 **班级邀请码多学生可用 / 学生绑定码多家长可用** 实现；「一次性」语义落在
> **可随时重新生成、旧码立即失效** 上。

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

按端/形态拆分为四个**相互独立**的模块。每个模块可单独启动、单独打包、单独发版，
任一模块的构建/发布**不影响**其他模块——彼此唯一的耦合是服务端接口契约。

- zg-tsp-server 服务端模块
- zg-tsp-web web 管理端模块
- zg-tsp-ios iOS 移动端模块
- zg-tsp-android Android 移动端模块

```
workspace/                            # 五个独立仓库同级检出（联调用）
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
├── zg-tsp-web/                       # Web 管理端（React 18 + Vite）
│   ├── src/
│   │   ├── api/
│   │   ├── pages/
│   │   │   ├── admin/                # 邀请码/用户/规则/文章/班级/概览
│   │   │   ├── teacher/              # 班级/作业/文章/积分概览
│   │   │   └── common/               # 登录/注册/强制改密
│   │   ├── components/
│   │   ├── store/
│   │   └── router/
│   ├── .env.example                  # VITE_API_BASE_URL
│   ├── package.json                  # 依赖独立，不引用其他模块
│   └── Dockerfile + nginx.conf
│
├── zg-tsp-ios/                       # iOS 移动端（Flutter，四角色）
│   ├── .gitignore
│   └── ...                           # Flutter 工程，产出 .ipa
│
└── zg-tsp-android/                   # Android 移动端（Flutter，四角色）
    ├── .gitignore
    └── ...                           # Flutter 工程，产出 .apk / .aab
```

> **仓库形态（决策 6）**：上述五个目录是**五个独立 git 仓库**，各自检出、
> 提交、发版。聚合检出仅为联调方便 —— 各模块始终可单独检出、单独安装依赖、
> 单独启动、单独打包（PRD 2.2.1）。

> **决策 6**：四个模块最终拆分为**独立仓库**发布，本目录为聚合与文档同步用；
> 接口契约以第 7 节为唯一权威来源。

#### 2.2.1 模块独立性原则

| 原则    | 说明                                                                  |
|-------|---------------------------------------------------------------------|
| 无源码依赖 | 任何模块不得 import / 引用其他模块源码；模块间**只通过 HTTP 接口**通信                       |
| 依赖自封闭 | 每个模块自带依赖清单（`requirements.txt` / `package.json` / Gradle），不使用根目录统一依赖 |
| 配置外置  | 服务端配置走 `.env`；Web 走 `VITE_*` 构建变量；移动端走各自配置项。**不硬编码**任何模块地址          |
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

健康检查：`POST /health` → `{code:0, data:{status:"ok"}}`

**zg-tsp-web**

```bash
cd zg-tsp-web
npm install
npm run dev                     # 开发，API 地址取 .env 的 VITE_API_BASE_URL
npm run build                   # 产出 dist/，纯静态文件
# 打包：docker build -t zg-tsp-web:1.0.0 .   （Nginx 托管 dist/）
```

部署时只需将 `dist/` 丢到任意静态服务器 / 对象存储；API 地址在构建期注入。

**zg-tsp-ios / zg-tsp-android**（技术栈：Flutter，决策 1）

```bash
cd zg-tsp-ios
flutter build ipa --flavor dev    --dart-define=API_BASE_URL=https://test.example.com
flutter build ipa --flavor prod   --dart-define=API_BASE_URL=https://api.example.com

cd zg-tsp-android
flutter build apk --flavor dev    --dart-define=API_BASE_URL=https://test.example.com
flutter build appbundle --flavor prod --dart-define=API_BASE_URL=https://api.example.com
```

产出 `.ipa` / `.aab` / `.apk`。**API 基地址**通过 `--dart-define` 在构建期注入，
配合 Flutter flavor（`dev` / `prod`）区分测试与生产渠道（决策 7），不硬编码在业务代码里。
两模块代码库同源，但**各自独立构建、独立签名、独立发版**。

> 打包环境（Xcode / CocoaPods / Android SDK / JDK / 签名）搭建见
> [开发环境搭建指南](ENV_SETUP.md)。亦可直接用一键脚本：
> `./scripts/build.sh ios|android [dev|prod]`（自动补齐渠道配置并归档产物）。

> - 学生端 / 家长端以移动端为主，移动优先布局；老师端 / admin 端以 Web 桌面端为主（移动端另有精简版，见 9.1）。
> - 移动端技术栈为 **Flutter**，四角色全覆盖（决策 1、2）。
> - 服务端接口清单见第 7 节，是四模块间唯一的契约来源。
> - **跨模块集成测试**：四模块各自可单测；跨端联调在 P9 统一进行，不作为模块独立性的约束。

---

## 3. 通用约定

### 3.1 请求规范

- 所有接口：`POST`
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

- 全 POST + Body，URL 不携带业务参数
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
    points           INTEGER DEFAULT 0,
    UNIQUE (homework_id, student_id)
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
    type        VARCHAR(20) NOT NULL, -- checkin/homework/reading/game/consume
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

> 所有积分发放统一读 `point_rules`，修改后立即生效；规则禁用则不发放。

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
- 登录之后可以自行修改当前账户密码

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

**时间采集**

- 「开始写作业」记录 `start_time`，重复点击不覆盖
- 「提交作业」记录 `submit_time`，`duration = submit - start`
- 超截止时间标记 `late`
- 用时 <1 分钟标记待审核（异常）

```
POST /homework/create   {class_id, title, description, subject, deadline}  teacher
POST /homework/list     {class_id, page, size}                             teacher
POST /homework/today    {}                                                 student
POST /homework/detail   {homework_id}                                      all
POST /homework/records  {homework_id}                                      teacher
POST /homework/delete   {homework_id}                                      teacher
POST /homework/start    {homework_id}                                      student
POST /homework/submit   multipart: homework_id, text_content, file?        student
```

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
POST /points/rank     {type: "day"|"total", page, size}   all
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
- 上传与导出的文件通过 `GET /uploads/<name>` 访问（静态挂载，非业务接口）

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

### 5.7 家长端 — 积分消耗

- 学生生成绑定码，家长输入绑定（可绑多个）
- 查看孩子积分与明细
- 消耗：预设事项（看手机-5、看电视-5、买玩具-20、买零食-10、自定义）
- 校验余额 ≥ 扣分，否则 400
- 写 PointLog（type=consume，points 为负，operator=家长）

```
POST /parent/bind          {bind_code}                    parent
POST /parent/children      {}                             parent
POST /parent/child-points  {student_id, page, size}       parent
POST /parent/consume       {student_id, item, points, remark} parent
POST /parent/consume-items {}                             parent
POST /parent/unbind        {student_id}                   parent
```

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
POST /homework/detail
POST /homework/records
POST /homework/delete
POST /homework/start
POST /homework/submit

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
POST /parent/consume
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
| 查看排行榜                        | 只读    | 只读      | 只读      | ❌       |
| 积分消耗                         | ❌     | ❌       | ❌       | ✅（绑定孩子） |
| 重新生成班级邀请码                  | ✅     | ✅（自己班级） | ❌       | ❌       |
| 重新生成学生绑定码                  | ✅     | ✅（本班学生） | ❌       | ❌       |
| 发布文章（纯文本/PDF/word）         | ✅     | ✅       | ❌       | ❌       |
| 导出文章 PDF                      | ✅     | ✅       | ✅      | ❌       |

> admin 不参与业务（不签到、不布置作业），不计入排行榜。

---

## 9. 前端页面清单

**四角色 × 两平台全覆盖**（决策 2 修订）：学生 / 家长 / 老师 / admin
在**移动端（zg-tsp-ios、zg-tsp-android）与 Web 端（zg-tsp-web）均提供**。

差异仅在**交互形态**，不在**功能覆盖**：

| 维度         | 移动端                          | Web 端                       |
|------------|------------------------------|----------------------------|
| 布局          | 移动优先，单列/卡片                     | 桌面优先，表格/抽屉/多列               |
| 复杂表格        | 简表 + 详情页                        | 完整表格、排序、筛选、批量编辑           |
| 富文本编辑      | 简化编辑器                           | 完整富文本编辑器                  |
| 文件上传        | 拍照 / 相册 / 文件选择                 | 拖拽上传 + 文件选择            |
| 批量操作       | 逐条操作                             | 多选批量（如成语题库批量导入）             |

> 任何功能不得仅存在于单一平台；若某功能在某平台形态受限，
> 需提供等效入口（如移动端「批量删除成语题目」→ 逐条删除）。

### 9.1 公共页面（移动端 + Web 端均提供）

- 登录页 / 注册页（选角色 student / parent / teacher；选 teacher 显示邀请码输入）
- admin 首次登录强制改密页
- 我的（个人资料、改密）

### 9.2 学生端（移动端 + Web 端均提供）

- 首页：签到、今日积分、今日作业、排行榜入口
- 作业列表 / 详情（开始写作业、上传提交）
- 阅读列表 / 详情（计时、心跳、读完标记、导出 PDF、只读）
- 游戏中心 / 数独 / 成语接龙
- 排行榜（日榜 / 总榜）
- 我的积分明细
- 我的（查看**绑定码**、所属班级、改密入口）
- 首次使用：加入班级页

### 9.3 家长端（移动端 + Web 端均提供）

- 孩子列表 / 绑定
- 孩子积分与明细
- 积分消耗（预设事项 + 自定义）

### 9.4 老师端（移动端 + Web 端均提供）

- 我的班级 / 班级学生列表（可重新生成班级邀请码 / 学生绑定码）
- 布置作业
- 作业完成情况（学生、状态、开始时间、提交时间、用时、积分）
- 文章管理 / 发布（纯文本 / PDF / word）/ 阅读记录 / 导出 PDF
- 班级积分概览

### 9.5 admin 端（移动端 + Web 端均提供）

- 邀请码管理（生成 / 列表 / 复制 / 撤销）
- 用户管理（全角色筛选、禁用 / 启用、重置密码；admin 行按钮置灰）
- 积分规则管理（积分值、日上限、扩展配置 JSON、启用开关）
- 文章管理（全量列表、编辑、上下架、删除、阅读统计）
- 发布文章（纯文本 / PDF / word）、导出 PDF
- 成语题库管理（批量导入 JSON / 文件、列表、编辑、启用开关、删除）
- 班级总览
- 数据概览（统计卡片）

### 9.6 平台实现分工

| 功能点           | zg-tsp-ios      | zg-tsp-android  | zg-tsp-web |
|----------------|---------------|---------------|-----------|
| 四角色登录 / 注册   | ✅             | ✅             | ✅         |
| 学生端全部功能     | ✅             | ✅             | ✅         |
| 家长端全部功能     | ✅             | ✅             | ✅         |
| 老师端全部功能     | ✅（移动形态）      | ✅（移动形态）      | ✅（桌面形态）   |
| admin 端全部功能   | ✅（移动形态）      | ✅（移动形态）      | ✅（桌面形态）   |
| 成语题库批量导入    | 逐条导入           | 逐条导入          | 批量导入      |

> iOS 与 Android 为**同源独立仓库**（决策 6），功能范围一致，各自独立构建与发版。
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
- 移动端适配（学生/家长），桌面优化（老师/admin）

### 10.4 初始化

- 启动种子：若无 admin 则创建（用户名 `admin`，密码取 `ADMIN_INIT_PASSWORD`，缺省随机打印日志）
- 启动种子：`point_rules` 默认规则（已存在则跳过）
- admin 首登强制改密

---

## 11. 开发计划

| Phase | 模块            | 内容                                                                      |
|-------|---------------|-------------------------------------------------------------------------|
| P0    | 四模块骨架         | 建立四模块目录与工程初始化；各模块依赖清单、配置外置（`.env.example`）、独立启动脚本、Dockerfile；确保无跨模块源码依赖 |
| P1    | zg-tsp-server | 建表、种子（admin+规则）、JWT 认证、注册登录（老师邀请码校验）                                    |
| P1.5  | zg-tsp-server | admin 基础：邀请码管理、用户管理（全角色禁用/启用）、全局统计                                      |
| P1.6  | zg-tsp-server | 积分规则管理：规则服务+缓存、admin CRUD、各积分点接入                                        |
| P2    | zg-tsp-server | 班级、作业布置、开始/提交打点                                                         |
| P3    | zg-tsp-server | 签到、PointLog、日榜/总榜、积分明细（读规则表）                                            |
| P4    | zg-tsp-server | 家长绑定与扣分                                                                 |
| P5    | zg-tsp-server | 阅读：文章发布（teacher/admin）、计时防挂机、阅读积分、admin 文章管理                            |
| P6    | zg-tsp-server | 游戏：数独、成语接龙、游戏积分与上限                                                      |
| P7    | zg-tsp-web    | **四角色**页面：学生 / 家长 / 老师 / admin（P1.5 起可并行开工）                            |
| P8    | ios / android | **四角色**页面：学生 / 家长 / 老师 / admin（P3 起可并行开工）                              |
| P9    | 全模块           | 联调、权限校验、防刷、适配、验收                                                        |

> 服务端 P1~P6 为关键路径，Web / 移动端在对应接口就绪后并行推进。
> 移动端与 Web 端均为**四角色全覆盖**（第 9 节），差异仅在交互形态，无功能缺口。

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
- [ ] 学生/家长端移动端可用
- [ ] 全接口均为 POST，URL 不携带业务参数

**迭代 v2.1（注册 / 班级码 / 阅读文档能力）**

- [ ] 注册用户名必须是手机号，格式非法返回 400
- [ ] 学生注册携带班级邀请码后自动入班；家长注册携带学生绑定码后自动绑定
- [ ] 班级邀请码可被多个学生使用；学生绑定码可被多个家长使用
- [ ] admin / 老师可重新生成班级邀请码与学生绑定码，旧码立即失效且已有关系不受影响
- [ ] 学生端可查看自己的绑定码（Web 与移动端均提供入口）
- [ ] 老师 / admin 可发布 PDF / word 文章，正文由服务端正确抽取
- [ ] 文章可导出为 PDF 且文件可正常打开
- [ ] 上传与导出的文件可通过 `/uploads/<name>` 访问

**模块独立性**

- [ ] 四个模块均可单独检出、单独安装依赖、单独启动，互不依赖其他模块的构建产物
- [ ] 任一模块重新构建/发版，不触发也不破坏其他模块
- [ ] 任一模块的源码中不含对其他模块的 import / 路径引用 / 构建期依赖
- [ ] 服务端不可用时，Web 与移动端能正常启动并给出降级提示，不崩溃
- [ ] 服务端地址均为外部配置项，代码中无硬编码地址
- [ ] 各模块可独立版本化发布；服务端小版本升级不强制客户端同步发版
- [ ] 移动端测试/生产渠道可分别打包，API 基地址由构建期参数注入
- [ ] 移动端四角色均可完成核心操作（老师布置作业、admin 管理用户/邀请码）
- [ ] **四角色 × 两平台功能对齐**：任一功能在移动端或 Web 端均不存在功能缺口
- [ ] 移动端批量操作有逐条等效入口（成语题库导入/删除等）
- [ ] admin 可导入成语题库（≥200 条），导入去重与校验生效；禁用题目学生端抽不到
- [ ] 服务端 `/health` 可用，未引入多余的监控依赖

---

## 13. 已确认的技术决策

以下事项已拍板，作为后续开发的既定前提：

| # | 事项       | 决策                                   | 影响                                         |
|---|----------|--------------------------------------|--------------------------------------------|
| 1 | 移动端技术栈   | **Flutter**（iOS + Android 同一代码库）     | `flutter build ipa` / `apk` 各自独立打包，满足模块独立性 |
| 2 | 角色 × 平台覆盖  | **四角色 × 两平台全覆盖**：学生/家长/老师/admin 在移动端与 Web 端均提供 | 三个客户端模块均为四角色全量功能，差异仅在交互形态，见第 9 节   |
| 3 | 多班级支持    | **不支持**，一个学生只属一个班级                   | `users.class_id` 单值，无需关联表                  |
| 4 | 成语接龙题库来源 | **后台导入**                             | 需新增 `idiom_questions` 表 + admin 导入接口 + 导入页 |
| 5 | 数独题库来源   | **内置生成算法**                           | 服务端按难度算法生成，无需预置题库                          |
| 6 | 仓库形态     | **四个独立仓库**，非 monorepo                | 各模块独立 clone/发版；本仓库仅作聚合与文档同步                |
| 7 | 环境渠道     | **测试 + 生产**（移动端两个渠道，Web 两套构建变量）      | 见 2.2.2；地址均外置，不硬编码                         |
| 8 | 健康检查与监控  | **仅 `/health`**，暂不引入就绪探针与 Prometheus | P0 仅需实现 `/health`                          |

### 13.1 决策衍生需求

- **决策 2 衍生**：移动端与 Web 端均为**四角色全量功能**，差异仅在交互形态
  （移动端简表/卡片，Web 端完整表格/抽屉/批量编辑）。
  **不得出现某功能仅存在于单一平台的情况**；移动端缺失的批量操作需提供逐条等效入口。
- **决策 4 衍生**：新增数据表与接口（补充至第 4、7 节）：
    - `idiom_questions` 表（成语题库，含答案、难度）
    - `POST /admin/idioms/import`（批量导入）、`POST /admin/idioms/list`
    - `POST /games/idiom/question`（学生端取题）
- **决策 6 衍生**：四模块拆分独立仓库后，接口契约需有唯一权威来源；
  本文档（第 7 节接口清单）即为契约基线，各仓库以其为准。
- **决策 8 衍生**：不引入监控依赖，`/health` 返回静态 `status`，不探测数据库连通性。

