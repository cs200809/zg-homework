# 设计规格：登录后自助修改当前账户密码（含 dev.sh 代码来源报告 + 全量同步独立仓库）

- 日期：2026-10-30
- 状态：已批准
- 触发：用户反馈「登录之后可以自助修改当前账户密码 这个功能未实现」（PRD 5.1 / 迭代.md 第 15 行）

## 1. 背景与根因

### 1.1 现象

用户在 Web 端找不到自助修改密码的入口。

### 1.2 根因

`scripts/dev.sh` 的 `REPOS_DIR` 探测顺序是 `../zg-tsp-repos` → `$ROOT` → `~/zg-tsp-repos`，**默认命中的是独立仓库** `../zg-tsp-repos/`，而不是本聚合快照。独立仓库的 Web 端是本快照的落后子集，缺少改密入口。

实测差异（`diff -rq`）：

| 能力 | 本快照 `zg-tsp-web/` | 独立仓库 `../zg-tsp-repos/zg-tsp-web/` |
|------|---------------------|------------------------------------------|
| Header 右上角下拉「修改密码」 | 有 | **无**（只有「退出登录」） |
| 学生端「我的」页 | 有 `Profile.tsx` | **无此页** |
| `/change-password` 路由 | 有 | 有 |
| `ChangePassword.tsx` 页面 | 有 | 有 |
| `authApi.changePassword` | 有 | 有 |

服务端 `POST /auth/change-password` 两边都存在且可用，缺口只在入口与若干加强项。

### 1.3 独立仓库相对快照的差异规模

源码层面独立仓库是快照的**严格子集**，无任何独占文件（`build/`、`.dart_tool/`、`uploads/` 等运行产物除外）：

| 模块 | 源码差异 | 内容 |
|------|---------|------|
| `zg-tsp-server` | ~12 个 `.py` | 快照多出 `services/document_service.py`、`utils/upload.py`、`utils/codes.py`、`seed/migrate_v21.py`；`entities.py` 多 3 列 |
| `zg-tsp-web` | 16 处 | 快照多出 `pages/student/Profile.tsx`；其余 14 个文件是注册三类码、文章 PDF 导出、重新生成邀请码/绑定码 |
| `zg-tsp-android` / `zg-tsp-ios` | 各 8 个 `lib/` 文件 | 注册三类码、PDF 导出 |
| `zg-tsp-docs` | 6 处 | 文档 |

独立仓库的 21 个未提交已跟踪改动（服务端 `security.py` / `requirements.txt` / `tests/*`、Android gradle 镜像适配与签名、iOS pubspec、docs `config.md` 等）**已逐文件核对，全部被快照吸收**，快照严格领先。全量 `split` 重建不会丢失任何源码内容。

## 2. 目标

1. Web 端与移动端在**所有角色**下都能自助修改当前账户密码，入口明确可达。
2. 服务端补齐密码强度校验，与两端前端对齐。
3. `scripts/dev.sh` 启动前明确报告"跑的是哪份代码、代码有多新"，杜绝本轮这类静默不同步问题。
4. 本快照与五个独立仓库同步一致，独立仓库可直接验收。

## 3. 非目标（明确不做）

| 不做的事 | 理由 |
|---------|------|
| 改密后使旧 token 失效 | JWT 无状态，实现需给 user 加 token 版本号并改全部鉴权路径，与本轮目标无关 |
| 给 teacher/parent/admin 补 Web「我的」页 | Header 右上下拉已是全角色通用入口，补页属额外范围 |
| 服务端限流实现 | 独立已知缺陷，不在本轮范围 |
| 重构 `api/parent.ts` 的职责错位 | 独立已知缺陷，不在本轮范围 |

## 4. 设计

### 4.1 服务端：密码强度校验

**文件**：`zg-tsp-server/app/schemas/auth.py`

`ChangePasswordRequest.new_password` 增加 `min_length=6` 约束，与 Web 端（`min: 6`）和移动端（`length < 6`）前端校验对齐。

现状：≥6 位只在两端前端校验，直接调 `POST /auth/change-password` 可设置 1 位密码。

`zg-tsp-server/app/routers/auth.py` 的 `change_password` 逻辑不变（已有原密码校验、新旧密码不得相同校验）。

### 4.2 Web 端：路由守卫与返回来源

**文件**：`zg-tsp-web/src/router/index.tsx`

新增 `RequireAuth` 守卫组件：只校验"已登录"（`token` 与 `user` 均存在），**不限角色、不套 `AdminLayout`**（改密页是全屏居中卡片，不是布局内页面）。

`/change-password` 从裸路由改为：

```
<Route path="/change-password" element={<RequireAuth><ChangePasswordPage /></RequireAuth>} />
```

现状：游客可直接打开 `/change-password`，提交时才 401。

`RequireAuth` **不检查** `must_change_password` —— 该状态下用户本来就该停在这个页面上，若检查会形成重定向循环。

**文件**：`zg-tsp-web/src/pages/common/ChangePassword.tsx`

改密成功后的跳转分两种：

- 强制模式（`user.must_change_password === true`）：`navigate(ROLE_HOME[user.role], { replace: true })` —— 保持现状
- 自助模式：`navigate(from ?? ROLE_HOME[user.role], { replace: true })` —— 回到**来源页**而不是强制跳角色首页

来源通过 React Router 的 location state 传递。两处入口都要传：

- `src/components/AdminLayout.tsx` 的下拉菜单项
- `src/pages/student/Profile.tsx` 的「修改密码」按钮

```tsx
navigate('/change-password', { state: { from: location.pathname } })
```

页面内取值：`const location = useLocation()`，`const from = (location.state as { from?: string } | null)?.from`。

### 4.3 移动端：改密页拆分

**文件（新增）**：`zg-tsp-android/lib/pages/common/change_password_page.dart`、`zg-tsp-ios/lib/pages/common/change_password_page.dart`

把 `ChangePasswordPage` 从 `login_page.dart` 搬到这个新文件，修正职责错位（登录页文件里塞着改密页）。

引用方改为 import 新文件：

- `lib/pages/common/login_page.dart`（移除类定义，改为 import；文件头注释「登录 / 注册 / 修改密码页」改为「登录 / 注册页」）
- `lib/main.dart`
- `lib/pages/common/profile_page.dart`（当前为拿 `ChangePasswordPage` 而 import `login_page.dart`）

新文件所需 import：`package:flutter/material.dart`、`package:provider/provider.dart`、`../../core/api_client.dart`（`errorMessage`）、`../../core/apis.dart`（`AuthApi`）、`../../state/auth_state.dart`（`AuthState`）、`../../widgets/common.dart`（`showSnack`）。

**行为不变**：

- 强制模式：改密成功后 `AuthState.markPasswordChanged()` 触发 `notifyListeners()`，`RootGate` 自动切到角色首页，页面自身不跳转
- 自助模式：`Navigator.pop()` 返回来源页

Android 与 iOS 两份**手工同步**（仓库无 CI 校验）。

### 4.4 `scripts/dev.sh`：代码来源与新鲜度报告

**文件**：`scripts/dev.sh`

在 `find_repos_dir` 解析完成之后、启动任何模块**之前**输出报告。

报告内容：

```
==> 代码来源
  REPOS_DIR = /Users/zg/PycharmProjects/zg-tsp-repos   （默认探测命中）
  ⚠ 当前跑的是独立仓库，与本快照 /Users/zg/PycharmProjects/zg-tsp 不同步
  模块 git 状态：
    zg-tsp-server   main  7dd7ba6   10 个已跟踪改动 / 5 个未跟踪
    zg-tsp-web      main  7dd7ba6   干净
    zg-tsp-android  main  7dd7ba6   8 个已跟踪改动
    ...
  与本快照的差异：server 12 处 / web 16 处 / android 8 处 / ios 8 处 / docs 6 处
```

实现要点：

1. **命中来源**：记录 `REPOS_DIR` 是来自环境变量还是默认探测（`../zg-tsp-repos` → `$ROOT` → `~/zg-tsp-repos`）
2. **同步警告**：`REPOS_DIR != ROOT` 时显式提示"跑的不是本快照"
3. **模块 git 状态**：对每个模块目录，若 `git -C <dir> rev-parse --is-inside-work-tree` 成功，输出分支、`HEAD` 短 hash、已跟踪改动数、未跟踪数；不是 git 目录则说明
4. **与快照差异**：用 `diff -rq` 逐模块统计，排除 `.git`、`node_modules`、`dist`、`build`、`.dart_tool`、`.gradle`、`.venv`、`__pycache__`、`.dev-logs`；仅在 `REPOS_DIR != ROOT` 且快照下五个模块都存在时统计
5. **POSIX `sh` 兼容**：不使用数组、`[[ ]]`、进程替换（与现有脚本约束一致）
6. `status` 命令复用同一份报告

### 4.5 文档与验收脚本

**文件**：`zg-tsp-docs/scripts/acceptance_check.py`

新增一组自助改密断言：登录 → 改密 → 用新密码登录成功 → 用新密码可调业务接口 → 改回原密码。

**文件**：`zg-tsp-docs/sys_doc/PRD.md`

第 28 行迭代条目 11「登录后可自助修改当前账户密码」标记完成，并说明入口位置（Web 右上角菜单 / 学生「我的」页 / 移动端「我的」页）。

**文件**：`zg-tsp-docs/sys_doc/迭代.md`

第 15 行对应条目标记完成。

## 5. 同步与验收流程

顺序：**先在快照做完并验收通过，再同步**（避免把半成品带到独立仓库）。

| 步骤 | 动作 | 验证方式 |
|------|------|---------|
| 1 | 快照完成 §4.1–§4.5 改动 | `npm run build`（Web，含 tsc 类型检查）、`flutter analyze`（两端）、`python -m app.seed.initial_data` + 服务端启动 |
| 2 | 跑业务验收 | `python zg-tsp-docs/scripts/acceptance_check.py`（需服务端已启动且可连 MySQL） |
| 3 | 提交快照改动 | `git commit`（`git subtree split` 只取提交历史，工作区未提交改动不会带入） |
| 4 | 全量重建独立仓库 | `./scripts/split_repos.sh split` —— `rm -rf ../zg-tsp-repos/*` 后从快照 subtree split 重建；源码零丢失（已逐文件核对） |
| 5 | 独立仓库服务端数据迁移 | `python -m app.seed.migrate_v21` —— `articles` 表新增 `file_url` / `file_name` / `file_type` 三列，脚本幂等 |
| 6 | 独立仓库复验 | 重跑 `acceptance_check.py`；Web 端 `npm run build`；两端 `flutter analyze` |

### 5.1 风险与缓解

| 风险 | 缓解 |
|------|------|
| `split` 的 `rm -rf` 抹掉独立仓库未提交改动 | 已逐文件核对：独立仓库无独占源码，其未提交改动全部被快照吸收，零丢失 |
| 独立仓库服务端表结构落后 | `migrate_v21.py` 幂等，且 `create_all()` 只建缺失表不阻塞 |
| `subtree split` 不含未提交改动 | 流程强制先 commit 再 split |
| 全量同步带入未验收的迭代 v2.1 功能 | 本轮先在快照完成验收再 split；独立仓库复验为最后一道关 |

## 6. 验收标准

1. Web 端：teacher / parent / admin / student 四个角色登录后，均可通过右上角头像下拉「修改密码」进入改密页；学生另可从「我的」页进入
2. Web 端：未登录访问 `/change-password` 被重定向到 `/login`
3. Web 端：自助改密成功后回到来源页，而非强制跳角色首页
4. Web 端：改密成功后 `must_change_password` 的强制跳转逻辑不变
5. 移动端（Android + iOS）：四角色「我的」页均可进入改密页，改密成功返回来源页；强制改密流程不变
6. 服务端：`POST /auth/change-password` 拒绝长度 < 6 的新密码，返回 400 与中文消息
7. `scripts/dev.sh` 启动前输出代码来源与新鲜度报告；指向独立仓库时明确警告
8. `acceptance_check.py` 新增的自助改密断言通过
9. 同步后独立仓库与快照源码一致，`git status` 干净
