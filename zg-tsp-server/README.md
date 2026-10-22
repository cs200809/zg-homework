# zg-tsp-server

学校兴趣培养积分系统 —— 服务端模块。

## 独立性

本模块**可单独检出、单独启动、单独打包**，不依赖仓库内其他模块：

- 与客户端**仅通过 HTTP 接口**通信，不引用任何其他模块源码
- 依赖自封闭：`requirements.txt` 为唯一依赖清单
- 配置外置：`.env`（从 `.env.example` 复制），代码中不硬编码密钥
- 服务端不可用不影响任何客户端的构建

## 启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 生产环境务必修改 JWT_SECRET 与 CORS_ORIGINS

# 3. 运行
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl -X POST http://127.0.0.1:8000/health
# {"code":0,"message":"ok","data":{"status":"ok","env":"dev"}}
```

## 打包

```bash
docker build -t zg-tsp-server:1.0.0 .
docker run -d -p 8000:8000 --env-file .env zg-tsp-server:1.0.0
```

## 目录结构

```
app/
├── main.py          应用入口（lifespan 建表 + 统一异常处理）
├── config.py        配置（读 .env）
├── db/session.py    引擎与会话（MySQL + 连接池）
├── db/repo.py       仓储层（SQLAlchemy 实现）
├── models/
│   ├── constants.py    枚举常量（角色、状态等）
│   └── entities.py     SQLAlchemy 模型（14 张表）
├── schemas/         Pydantic 出入参
├── routers/         路由：auth / admin / classes / homework /
│                    point_rules_admin / checkin / points /
│                    articles / games / parent
├── services/        point_rule_service（60s 缓存）/ point_service
├── utils/           security(jwt/bcrypt) / deps(权限依赖) / response
├── seed/            建表与种子脚本（python -m app.seed.initial_data）
└── uploads/         上传文件（git 忽略内容）

tests/               pytest 测试
```

## 数据库：MySQL

数据落在 MySQL `zg_tsp`，字符集 **utf8mb4**（正确存储中文与 emoji）。

```bash
# 1. 建表 + 种子（幂等，可重复执行）
python -m app.seed.initial_data

# 2. 清库重建（危险，仅开发用）
python -m app.seed.initial_data --reset
```

> 连接配置在 `.env` 的 `DATABASE_URL`。
> **种子不随服务启动自动执行** —— lifespan 只做 `create_all` 建表（幂等），
> 避免生产环境意外写入默认账号。

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
> 当前 `admin` 的随机密码已打印过一次（`WR2k_lUsudpm8XY3`），
> 建议改密或用 `--reset` 重建。

## 测试

```bash
pytest                    # 172 个用例
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
- **通用**：统一响应格式、无入参接口接受空 Body

> **测试库约定：只增不删**
>
> 测试直接跑在开发库 `zg_tsp` 上（不另建测试库）。为保证用例互不干扰：

> - 每个用例用**随机后缀的唯一用户名**（如 `t_a1b2c3_stu01`），天然不冲突
> - 只做 INSERT / UPDATE，**从不 TRUNCATE、从不 DELETE**
> - 代价是测试数据会残留在库中（users 表约 700+ 条测试记录）
> - **规则表也是共享状态**：改规则的用例必须用 `set_rule` 夹具自备前置条件，
   不能依赖种子默认值（否则受其他用例影响）
>
> 需要干净起点时手动执行 `python -m app.seed.initial_data --reset`。

## 接口契约

全 POST + Body，参数不携带于 URL。统一响应 `{code, message, data}`。
完整清单见 PRD 第 7 节（`sys_doc/PRD.md`）—— 这是与其他模块的唯一契约来源。

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

## 开发进度

- [x] P0 骨架：配置、health 检查、Dockerfile、目录结构
- [x] P1 JWT 认证 + 注册登录
- [x] P1b 接入 MySQL：14 张表 + 种子数据
- [x] P1.5 admin 基础：邀请码管理、用户管理、全局统计
- [x] P1.6 积分规则管理 + 积分发放服务
- [x] P2 班级与作业（172 测试通过）
- [ ] P3 签到与积分
- [ ] P4 家长绑定扣分
- [ ] P5 阅读
- [ ] P6 游戏（含成语题库导入）