# 学校兴趣培养积分系统 — 完整 PRD（v2.0）

> 版本：v2.0（合并 admin 模块与权限扩展）  
> 技术栈：React + Ant Design 前端 / Python FastAPI 后端 / JWT 认证  
> 接口约定：**全部使用 POST，参数走 Body**，避免 URL 信息泄露  
> 文档目的：作为 LLM 直接开发项目的唯一依据

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
- **数据库**：SQLite（MVP，可平滑迁移 MySQL）
- **认证**：JWT（python-jose），密码 bcrypt 加密
- **文件存储**：本地 `uploads/`（预留 OSS 接口）
- **部署**：前后端分离，Nginx 反代（可选）

### 2.2 项目结构

按端/形态拆分为四个独立模块（各自可独立构建、独立发布版本）：

- zg-tsp-server 服务端模块
- zg-tsp-web web 管理端模块
- zg-tsp-ios iOS 移动端模块
- zg-tsp-android Android 移动端模块

```
project/
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
│   └── requirements.txt
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
│   └── package.json
│
├── zg-tsp-ios/                       # iOS 移动端（学生 / 家长）
│   └── ...                           # Swift / SwiftUI 或 Flutter
│
├── zg-tsp-android/                   # Android 移动端（学生 / 家长）
│   └── ...                           # Kotlin 或 Flutter
│
└── sys_doc/
    └── PRD.md
```

> - 学生端 / 家长端以移动端为主，移动优先布局；老师端 / admin 端以 Web 桌面端为主。
> - 移动端具体技术栈待定，需在开工前确认（见文末「待确认事项」）。
> - 四模块共用服务端 `/api` 接口契约，接口清单见第 7 节。

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
```

**索引**：`point_logs(student_id, log_date)`、`homework_records(student_id)`、`users(class_id)`、
`teacher_invite_codes(code/status)`、`point_rules(rule_key)`

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

- 学生：用户名+密码+角色 → 注册后输班级邀请码加入
- 家长：用户名+密码+角色 → 注册后输学生绑定码
- 老师：用户名+密码+角色+**老师邀请码**（必填，校验存在/未用/未过期，一码一用）
- admin：不开放注册，种子初始化（`ADMIN_INIT_PASSWORD` 环境变量，缺省随机打印日志）

**登录**

- 用户名+密码 → JWT（含 user_id、role）
- admin 首次登录返回 `must_change_password: true`，未改密前其他接口 403
- 被禁用用户登录返回 403

**规则**

- 用户名唯一，3~20 位；密码 ≥6 位
- JWT 有效期 7 天，前端 localStorage

**接口**

```
POST /auth/register        {username, password, role, nickname, teacher_invite_code?}
POST /auth/login           {username, password} → {token, user, must_change_password?}
POST /auth/me              {}
POST /auth/change-password {old_password, new_password}
```

---

### 5.2 班级管理

- 老师创建班级（名称），生成 6 位邀请码
- 学生凭邀请码加入（一个学生只属一个班级）
- 老师查看班级学生、移除学生

```
POST /classes/create         {name}                          teacher
POST /classes/join           {invite_code}                   student
POST /classes/my             {}                              teacher/student
POST /classes/students       {class_id}                      teacher
POST /classes/remove-student {class_id, student_id}          teacher
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

**积分**（读规则表）

- 每分钟 +1，单篇上限 10，日上限 30
- 读完 +5，单篇 1 次

```
POST /articles/create    {title, cover, content}          teacher/admin
POST /articles/list      {page, size}                     all（仅 published）
POST /articles/detail    {article_id}                     all
POST /articles/heartbeat {article_id, seconds}            student
POST /articles/finish    {article_id}                     student
POST /articles/records   {article_id}                     teacher
POST /articles/delete    {article_id}                     teacher（仅自己）
```

---

### 5.6 课后小游戏

**数独**：难度分级，计时，完成提交按难度给分（规则表）
**成语接龙**：60 秒限时闯关，答对 +1/题，题库内置 200+
**防沉迷**：每日游戏总积分上限 20（规则表 daily_limit）

```
POST /games/sudoku/start   {difficulty}                  student
POST /games/sudoku/result  {puzzle_id, duration, success} student
POST /games/idiom/start    {}                            student
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
POST /articles/list
POST /articles/detail
POST /articles/heartbeat
POST /articles/finish
POST /articles/records
POST /articles/delete

# 游戏
POST /games/sudoku/start
POST /games/sudoku/result
POST /games/idiom/start
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
POST /admin/articles/list
POST /admin/articles/detail
POST /admin/articles/update
POST /admin/articles/toggle
POST /admin/articles/delete
POST /admin/articles/stats
POST /admin/classes/list
POST /admin/stats/overview
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

> admin 不参与业务（不签到、不布置作业），不计入排行榜。

---

## 9. 前端页面清单

按模块归属划分：

### 9.1 zg-tsp-ios / zg-tsp-android（移动端，学生 + 家长）

**公共**

- 登录页 / 注册页（选角色 student/parent）
- 学生首次：加入班级页
- 家长首次：绑定学生页
- 我的（个人资料、改密）

**学生端**

- 首页：签到、今日积分、今日作业、排行榜入口
- 作业列表/详情（开始、上传）
- 阅读列表/详情（计时）
- 游戏中心/数独/成语接龙
- 排行榜（日榜/总榜）
- 我的积分明细

**家长端**

- 孩子列表/绑定
- 孩子积分与明细
- 积分消耗

### 9.2 zg-tsp-web（Web 管理端，老师 + admin）

**公共**

- 登录页 / 注册页（选角色 teacher；显示邀请码输入）
- admin 首次登录强制改密页

**老师端（桌面）**

- 班级管理/创建
- 作业列表/布置/完成情况表格
- 文章管理/发布/阅读记录
- 班级积分概览

**admin 端（桌面）**

- 邀请码管理（生成/列表/复制/撤销）
- 用户管理（全角色筛选、禁用/启用、重置密码，admin 行按钮置灰）
- 积分规则管理（表格+行内编辑弹窗+JSON 编辑器+启用开关）
- 文章管理（全量列表、编辑抽屉、上下架、删除、阅读统计）
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
- 文件白名单 jpg/png/pdf ≤10MB
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

| Phase | 模块              | 内容                                           |
|-------|-----------------|----------------------------------------------|
| P0    | 四模块骨架          | 建立 zg-tsp-server / web / ios / android 目录与工程初始化         |
| P1    | zg-tsp-server    | 建表、种子（admin+规则）、JWT 认证、注册登录（老师邀请码校验）        |
| P1.5  | zg-tsp-server    | admin 基础：邀请码管理、用户管理（全角色禁用/启用）、全局统计         |
| P1.6  | zg-tsp-server    | 积分规则管理：规则服务+缓存、admin CRUD、各积分点接入             |
| P2    | zg-tsp-server    | 班级、作业布置、开始/提交打点                              |
| P3    | zg-tsp-server    | 签到、PointLog、日榜/总榜、积分明细（读规则表）                 |
| P4    | zg-tsp-server    | 家长绑定与扣分                                      |
| P5    | zg-tsp-server    | 阅读：文章发布（teacher/admin）、计时防挂机、阅读积分、admin 文章管理 |
| P6    | zg-tsp-server    | 游戏：数独、成语接龙、游戏积分与上限                           |
| P7    | zg-tsp-web       | 老师端 + admin 端页面（P1.5 起可并行开工）                    |
| P8    | ios / android    | 学生端 + 家长端页面（P3 起可并行开工）                        |
| P9    | 全模块            | 联调、权限校验、防刷、适配、验收                          |

> 服务端 P1~P6 为关键路径，Web / 移动端在对应接口就绪后并行推进。

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

---

## 13. 待确认事项

开工前需拍板，否则影响 P0/P8：

1. **移动端技术栈**
   - 选项 A：Flutter（iOS + Android 同一代码库，两端一致）
   - 选项 B：原生双端（iOS SwiftUI + Android Kotlin，各自维护）
   - 影响：P8 工作量与人力；选 A 可大幅压缩开发周期。
2. **移动端是否需要老师/admin 功能** — 当前 PRD 划分老师/admin 只做 Web。若移动端也要，需补充页面清单。
3. **多班级支持** — 当前「一个学生只属一个班级」。是否需要学生跨班/多班？
4. **成语接龙题库 200+ 来源** — 内置 JSON / 数据库表 / 后台导入？
5. **数独题库来源** — 内置生成算法 / 预置题库？
6. **部署形态** — 是否需要 Docker Compose 一键部署？

