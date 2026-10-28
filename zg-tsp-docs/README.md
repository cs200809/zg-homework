# zg-tsp-docs

学校兴趣培养积分系统 —— **文档与验收仓库**。

本仓库是跨模块的**唯一权威契约来源**。四个功能模块各自独立仓库发布，
接口契约以本仓库的 [PRD](sys_doc/PRD.md) 为准。

## 内容

| 路径 | 说明 |
|------|------|
| `sys_doc/PRD.md` | 完整产品需求文档 v2.0 —— 数据模型、接口清单、权限矩阵、验收标准 |
| `sys_doc/config.md` | 各环境配置项（数据库等） |
| `sys_doc/ENV_SETUP.md` | 开发环境搭建指南 —— Xcode / CocoaPods / Android SDK / JDK / 签名配置 |
| `scripts/acceptance_check.py` | 业务验收脚本：对照 PRD 第 12 节逐条调真实接口验证 |
| `scripts/independence_check.py` | 模块独立性静态检查：依赖自封闭、零跨模块引用、无硬编码地址 |

## 四个模块仓库

| 仓库 | 内容 | 技术栈 |
|------|------|--------|
| [zg-tsp-server](https://github.com/your-org/zg-tsp-server) | 服务端 | Python 3.12 / FastAPI / SQLAlchemy 2.0 / MySQL 8 |
| [zg-tsp-web](https://github.com/your-org/zg-tsp-web) | Web 管理端 | React 18 / Vite 6 / Ant Design 5 |
| [zg-tsp-ios](https://github.com/your-org/zg-tsp-ios) | iOS 移动端 | Flutter 3.47 / Dart 3.13 |
| [zg-tsp-android](https://github.com/your-org/zg-tsp-android) | Android 移动端 | Flutter 3.47 / Dart 3.13 |

**四角色 × 两平台全覆盖**：学生 / 家长 / 老师 / admin 在移动端与 Web 端均提供，
差异仅在交互形态（PRD 第 9 节）。

## 聚合检出（联调用）

四个模块独立仓库，联调时需同级检出：

```
workspace/
├── zg-tsp-docs/       ← 本仓库
├── zg-tsp-server/
├── zg-tsp-web/
├── zg-tsp-ios/
└── zg-tsp-android/
```

各模块仍可**单独检出、单独安装依赖、单独启动、单独打包**（PRD 2.2.1），
聚合检出只是为了让 Vite 代理与验收脚本能同时访问各模块。

## 验收脚本用法

需在聚合目录下运行（脚本会定位同级的 `zg-tsp-server`）：

```bash
# 1. 启动服务端
cd zg-tsp-server && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. 业务验收（PRD 第 12 节）
python zg-tsp-docs/scripts/acceptance_check.py

# 3. 独立性检查
python zg-tsp-docs/scripts/independence_check.py
```

> `acceptance_check.py` 会自动确保 admin 可登录（必要时重置本地库密码）。
> 两个脚本都只读或写测试数据，**不删表**。

## 接口契约

全 POST + Body，参数不携带于 URL。统一响应：

```json
{ "code": 0, "message": "ok", "data": {} }
```

错误码：`0` 成功 / `400` 参数错误 / `401` 未认证 / `403` 无权限 /
`404` 不存在 / `429` 限流 / `500` 服务端错误

完整接口清单见 [PRD 第 7 节](sys_doc/PRD.md)。

## 变更约定

PRD 是跨模块契约，**修改 PRD 需同步通知四个模块仓库**：

- 新增/修改接口 → 服务端实现后，各客户端同步
- 修改字段语义（如 `daily_limit` 含义）→ 四个模块都要改
- 数据模型变更 → 服务端迁移 + 客户端类型定义同步

各模块的客户端类型定义（`types.ts` / `models.dart`）以 PRD 为准，
但**它们是各自仓库的副本**，改 PRD 后需手动同步。
