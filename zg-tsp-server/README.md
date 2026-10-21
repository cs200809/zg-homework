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
├── main.py          应用入口（lifespan 种子 + 统一异常处理）
├── config.py        配置（读 .env）
├── db/repo.py       仓储层（当前内存 Mock，后续换 SQLAlchemy）
├── models/          数据实体
├── schemas/         Pydantic 出入参
├── routers/         路由：auth/classes/homework/checkin/points/
│                    articles/games/parent/admin
├── services/        point_rule_service / point_service / anti_cheat
├── utils/           security(jwt/bcrypt) / deps(权限依赖) / response
├── seed/            admin + point_rules + 联调账号初始化
├── data/            SQLite 数据文件（git 忽略）
└── uploads/         上传文件（git 忽略内容）

tests/               pytest 测试
```

## 当前状态：Mock 数据（P1）

P1 阶段**尚未建表**，数据存于进程内存（`app/db/repo.py`）：

- **进程重启数据丢失**，仅供接口联调
- `routers` / `services` 只通过 `repo` 访问数据，不直接碰列表
- 接入 SQLAlchemy 时**只需替换 `app/db/repo.py`**，调用方签名不变

### 启动时自动创建

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

> admin 密码随机生成，启动日志中会打印一次。

## 测试

```bash
pytest                    # 27 个用例
```

覆盖：登录/注册、四角色权限、老师邀请码一码一用（含过期/撤销）、
禁用后 JWT 立即失效、admin 强制改密、参数校验、统一响应格式。

## 接口契约

全 POST + Body，参数不携带于 URL。统一响应 `{code, message, data}`。
完整清单见 PRD 第 7 节（`sys_doc/PRD.md`）—— 这是与其他模块的唯一契约来源。

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

## 开发进度

- [x] P0 骨架：配置、health 检查、Dockerfile、目录结构
- [x] P1 JWT 认证 + 注册登录（**Mock 数据层**，27 测试通过）
- [ ] P1b 接入 SQLAlchemy 真实建表（替换 `app/db/repo.py`）
- [ ] P1.5 admin 基础
- [ ] P1.6 积分规则管理
- [ ] P2 班级与作业
- [ ] P3 签到与积分
- [ ] P4 家长绑定扣分
- [ ] P5 阅读
- [ ] P6 游戏（含成语题库导入）