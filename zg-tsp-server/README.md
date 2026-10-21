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
├── main.py          应用入口
├── config.py        配置（读 .env）
├── models/          SQLAlchemy 模型
├── schemas/         Pydantic 出入参
├── routers/         路由：auth/classes/homework/checkin/points/
│                    articles/games/parent/admin
├── services/        point_rule_service / point_service / anti_cheat
├── utils/           jwt / deps(权限依赖) / response
├── seed/            admin + point_rules 初始化
├── data/            SQLite 数据文件（git 忽略）
└── uploads/         上传文件（git 忽略内容）
```

## 接口契约

全 POST + Body，参数不携带于 URL。统一响应 `{code, message, data}`。
完整清单见 PRD 第 7 节（`sys_doc/PRD.md`）—— 这是与其他模块的唯一契约来源。

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

## 开发进度

- [x] P0 骨架：配置、health 检查、Dockerfile、目录结构
- [ ] P1 建表 + 种子 + JWT 认证 + 注册登录
- [ ] P1.5 admin 基础
- [ ] P1.6 积分规则管理
- [ ] P2 班级与作业
- [ ] P3 签到与积分
- [ ] P4 家长绑定扣分
- [ ] P5 阅读
- [ ] P6 游戏（含成语题库导入）