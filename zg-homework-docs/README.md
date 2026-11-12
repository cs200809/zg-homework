# zg-homework-docs

本目录是单一仓库中的文档与契约模块。[PRD](sys_doc/PRD.md) 是需求与接口契约的权威来源；服务端和 Web 分别位于同仓的 `zg-homework-server/`、`zg-homework-web/`，保留独立依赖与构建边界。微信小程序代码位于仓外的 `~/WeChatProjects/HomeworkPoints`，见 [小程序规划](sys_doc/小程序.md)。

## 内容

| 路径 | 说明 |
|---|---|
| `sys_doc/PRD.md` | 产品需求、接口契约和验收标准（v2.3） |
| `sys_doc/config.md` | 环境配置 |
| `sys_doc/小程序.md` | 小程序规划、分期与验收 |
| `sql/init.sql` | 从服务端 ORM 生成的部署 SQL |
| `scripts/independence_check.py` | 服务端与 Web 的静态模块边界检查 |
| `scripts/acceptance_check.py` | 通过真实接口执行的业务验收 |

## 检查与验收

在仓库根目录运行 `make check`，仅做静态模块边界检查，不连接数据库或服务端。它不覆盖仓外小程序，也不能替代运行时验收。

业务验收需服务端运行在 `http://127.0.0.1:8000`，并提供已有管理员密码：

```bash
ACCEPTANCE_ADMIN_PASSWORD='<admin密码>' make acceptance
```

**业务验收会通过真实接口创建持久数据并修改积分规则**，请仅对专用隔离数据库运行；脚本不会自动重置管理员密码。服务端 pytest 同样会写真实 MySQL，可能调用删除接口；测试目录被忽略，缺失或未收集到测试不算成功。

## 契约变更

接口或数据语义变化时，先更新 PRD，再同步服务端及各客户端。Web 的 `src/api/types.ts` 和小程序中的客户端定义是手工副本，须手动维护。业务接口通常使用 POST 和请求体；上传使用 multipart，静态文件和文档接口使用 GET。
