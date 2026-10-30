# 自助修改当前账户密码 + dev.sh 代码来源报告 + 全量同步独立仓库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Web 端与移动端的所有角色都能自助修改当前账户密码并补齐验收覆盖，给 `scripts/dev.sh` 加上"跑的是哪份代码、有多新"的启动前报告，最后把本快照全量同步到五个独立仓库并复验。

**Architecture:** 服务端 `POST /auth/change-password` 与 `ChangePasswordRequest` 契约**已满足**（`min_length=6` + 全局 `RequestValidationError` → 400），本轮不改服务端逻辑，只补端到端验收断言。Web 端加一个不限角色的 `RequireAuth` 守卫保护改密页，并让改密成功后回到来源页而非强制跳角色首页。移动端把 `ChangePasswordPage` 从 `login_page.dart` 拆到独立文件（Android/iOS 手工同步）。`scripts/dev.sh` 在启动任何模块前打印 REPOS_DIR 来源、五模块 git 状态、与本快照的差异文件数。

**Tech Stack:** Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8；React 18 / Vite 6 / Ant Design 5 / React Router 6；Flutter 3.47 / Dart 3.13；POSIX `sh`。

**Spec:** `docs/superpowers/specs/2026-10-30-self-service-password-change-design.md`

## Global Constraints

以下约束来自 `CLAUDE.md` 与代码现状，**每个 Task 都隐含包含**：

- **服务端响应契约**：所有业务接口 `POST` + JSON Body，响应固定 `{code, message, data}`，错误码 0/400/401/403/404/429/500。router 里抛 `HTTPException` 时 `detail` 必须是 `{"code": ..., "message": ...}` 字典。
- **服务端参数校验**：`app/main.py:86` 的 `RequestValidationError` 处理器已把 Pydantic 校验失败转成 **400 + `{code: 400, message}`**，不是 FastAPI 默认的 422。写断言时按 400 判，不要按 422。
- **服务端数据层**：Repo 方法只 `db.add()` + `db.flush()`，不 commit；commit 由 router 层负责。
- **服务端测试**：`zg-tsp-server/tests/` 已在 `.gitignore`（根仓库与 `zg-tsp-server/.gitignore` 都有），测试文件是**本地联调资产，不入库**。pytest 需要**可连的 MySQL**，不 mock、不用 sqlite；测试只 INSERT/UPDATE 从不 DELETE，跑完库里会留垃圾数据。
- **Web API 层**：`api/client.ts` 的 `post<T>()` 在 `payload.code !== 0` 时抛 `Error`（带 `code` 属性）。请求拦截器自动带 `Bearer` token（读 `localStorage`）。
- **Web 无测试框架**：仓库里没有 jest / vitest / testing-library，也没有 ESLint 配置。Web 侧唯一可用的自动验证是 `npm run build`（= `tsc -b && vite build --mode production`，含类型检查）。不要发明测试脚手架。
- **Web 无 401 全局拦截**：token 过期不会自动登出，别依赖它。
- **Web 路由**：改密页是**全屏独立页**，不套 `AdminLayout`。
- **移动端无路由表**：`MaterialApp` 只有 `home: RootGate`，**禁止 `Navigator.pushNamed`**，页面跳转一律 `Navigator.push(MaterialPageRoute(...))`。
- **移动端角色分流**：登录/改密后的跳转由 `RootGate` 监听 `AuthState` 自动完成，页面里**不要**写跳转。`RootGate` 用 `ValueKey('${id}:${role}')` 在账号变化时重建。
- **移动端两端必须手工同步**：`zg-tsp-android/lib/` 与 `zg-tsp-ios/lib/` 是物理复制的两份，无 CI 校验。差异只在包名（`zg_tsp_android` vs `zg_tsp_ios`）、`core/config.dart` 注释、`main.dart` 首行工程名注释。本轮的 `lib/` 改动必须两端都做，且 `main.dart` 首行保持各自工程名。
- **dev.sh 是 POSIX `sh`**：不能用数组、`[[ ]]`、进程替换、`$'\033'`。唯一非 POSIX 依赖是 `local`（sh/bash/zsh/dash 均支持，macOS 自带 ksh93u+ 不支持）。
- **构建必须指定 `REPOS_DIR`**：`scripts/build.sh` 与 `scripts/dev.sh` 的 `REPOS_DIR` 探测顺序是 `../zg-tsp-repos` → `$ROOT` → `~/zg-tsp-repos`，**默认命中独立仓库**。跑本快照代码要显式 `REPOS_DIR="$PWD"`。
- **提交落在 `main`**：`scripts/split_repos.sh split` 从当前 HEAD 做 `git subtree split`，工作区未提交的改动**不会**被带入。Task 7 之前必须先 commit。
- **不要动已知缺陷**：服务端限流未实现、Web 路由无懒加载、`api/parent.ts` 职责错位、移动端 5 个未使用依赖 —— 这些都不在本轮范围。

---

### Task 1: 服务端改密契约的端到端验收覆盖

服务端 `POST /auth/change-password` 与 `ChangePasswordRequest`（`min_length=6`）**已经满足契约**，本 Task 不改服务端代码，只在端到端验收脚本里把契约钉住。

**Files:**
- Modify: `zg-tsp-docs/scripts/acceptance_check.py`（在第 4 组"admin 禁用立即生效"之后插入第 18 组断言）
- Verify only (不改): `zg-tsp-server/app/schemas/auth.py:48-50`、`zg-tsp-server/app/routers/auth.py:172-189`、`zg-tsp-server/app/main.py:86-93`

**Interfaces:**
- Consumes: `acceptance_check.py` 已有的 `post(c, path, body, token)` 辅助函数、`check(ok, name, detail)` 辅助函数、`roles` 字典、`tokens` 字典（键 `teacher`/`student`/`parent`）、`class_invite` 变量。
- Produces: 验收结果中新增编号 `18.` ~ `18g.` 的断言行；不产出新的 Python 接口。

**背景**：`tokens["student"]` 对应的账号密码是 `test123456`（由 `admin_reset_pwd` 在验收脚本第 176/193/204 行设置）。第 4 组（脚本第 253-267 行）会临时禁用并恢复该学生账号，其内部硬编码 `test123456`，所以第 18 组必须**自己把密码改回原值**，否则第 4 组之后的断言（如同账号登录）会受影响。

- [ ] **Step 1: 确认服务端契约现状**

逐条核对并在终端验证（不需要改代码）：

```bash
cd /Users/zg/PycharmProjects/zg-tsp
sed -n '46,52p' zg-tsp-server/app/schemas/auth.py    # 期望：new_password: str = Field(..., min_length=6, max_length=64)
sed -n '172,190p' zg-tsp-server/app/routers/auth.py  # 期望：原密码校验 + 新旧不同校验 + must_change_password=False
sed -n '86,94p' zg-tsp-server/app/main.py            # 期望：RequestValidationError → 400 + fail(CODE_BAD_REQUEST, ...)
```

Expected: 三处输出与上述注释一致。**若 `min_length=6` 不存在，才在 `zg-tsp-server/app/schemas/auth.py` 的 `ChangePasswordRequest` 补上 `Field(..., min_length=6, max_length=64)`；若已存在则不改**（当前已存在）。

- [ ] **Step 2: 在验收脚本中插入第 18 组断言**

编辑 `zg-tsp-docs/scripts/acceptance_check.py`，在第 4 组断言块结束（第 267 行 `check(False, "4. 禁用立即生效", "未找到学生账号")` 之后）、第 5 组 `# 5. admin 无法禁用 admin`（第 269 行）之前插入：

```python
    # 18. 登录后可自助修改当前账户密码（PRD 5.1、迭代 v2.1 条目 11）
    #     入口：Web 右上角菜单 / 学生「我的」页；移动端四角色「我的」页
    #     注意：本组会临时改动学生密码，末尾必须改回 test123456，
    #     否则后续断言（该账号密码被硬编码为 test123456）会受影响。
    _old_pwd = "test123456"
    _new_pwd = "test654321"
    _stu_phone = roles["student"]

    # 18a. 原密码错误被拒
    r = post(c, "/auth/change-password",
             {"old_password": "wrong_password_xxx", "new_password": _new_pwd},
             token=tokens["student"])
    check(r.get("code") == 400, "18a. 改密：原密码错误被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18b. 新密码短于 6 位被拒（服务端 Pydantic min_length=6，与两端前端一致）
    r = post(c, "/auth/change-password",
             {"old_password": _old_pwd, "new_password": "12345"},
             token=tokens["student"])
    check(r.get("code") == 400, "18b. 改密：新密码短于 6 位被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18c. 新旧密码相同被拒
    r = post(c, "/auth/change-password",
             {"old_password": _old_pwd, "new_password": _old_pwd},
             token=tokens["student"])
    check(r.get("code") == 400, "18c. 改密：新旧密码相同被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18d. 原密码正确时改密成功
    r = post(c, "/auth/change-password",
             {"old_password": _old_pwd, "new_password": _new_pwd},
             token=tokens["student"])
    check(r.get("code") == 0, "18d. 改密：原密码正确时改密成功",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18e. 新密码可登录
    _login_new = post(c, "/auth/login", {"username": _stu_phone, "password": _new_pwd})
    check(_login_new.get("code") == 0, "18e. 改密：新密码可登录",
          f"code={_login_new.get('code')} {_login_new.get('message', '')}")

    # 18f. 旧密码失效
    _login_old = post(c, "/auth/login", {"username": _stu_phone, "password": _old_pwd})
    check(_login_old.get("code") != 0, "18f. 改密：旧密码登录失效",
          f"code={_login_old.get('code')}")

    # 18g. 改回原密码（JWT 无状态，原 token 仍可用）
    _back = post(c, "/auth/change-password",
                 {"old_password": _new_pwd, "new_password": _old_pwd},
                 token=tokens["student"])
    check(_back.get("code") == 0, "18g. 改密：可改回原密码（测试数据复原）",
          f"code={_back.get('code')} {_back.get('message', '')}")
```

- [ ] **Step 3: 起服务端并跑验收**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
# 1) 确认 MySQL 可连、.env 存在
ls zg-tsp-server/.env || cp zg-tsp-server/.env.example zg-tsp-server/.env
# 2) 建表 + 种子（幂等）
cd zg-tsp-server && python -m app.seed.initial_data && cd ..
# 3) 后台起服务端
( cd zg-tsp-server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/zgtsp-server.log 2>&1 & )
sleep 4
curl -s -X POST http://127.0.0.1:8000/health
```

Expected: `{"code":0,"message":"ok","data":{"status":"ok",...}}`

```bash
cd /Users/zg/PycharmProjects/zg-tsp
python zg-tsp-docs/scripts/acceptance_check.py
```

Expected: 末尾输出 `=== 业务验收：N/M 通过 ===`，且第 18 组 7 条断言全部为 ✅，未通过项列表里**没有** 18 开头的条目。

- [ ] **Step 4: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add zg-tsp-docs/scripts/acceptance_check.py
git commit -m "$(cat <<'EOF'
验收脚本补自助改密断言（PRD 5.1）

新增第 18 组 7 条断言：原密码错误被拒、新密码短于 6 位被拒、
新旧密码相同被拒、改密成功、新密码可登录、旧密码失效、可改回原密码。

服务端契约（ChangePasswordRequest.min_length=6 + 全局
RequestValidationError → 400）本就满足，本次只补验收覆盖。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Web 端改密页加登录守卫

改密页目前是裸路由，游客可直接打开 `/change-password`，提交时才 401。加一个不限角色、不套布局的守卫。

**Files:**
- Modify: `zg-tsp-web/src/router/index.tsx`（新增 `RequireAuth` 组件 + 改 `/change-password` 路由）
- Verify only: `zg-tsp-web/src/pages/common/ChangePassword.tsx`（本 Task 不改它）

**Interfaces:**
- Consumes: `useAuthStore()` 返回的 `{ token, user, initialized }`；`react-router-dom` 的 `Navigate`。
- Produces: `RequireAuth({ children: ReactElement }): ReactElement` —— 本文件内私有组件，不导出。供 Task 3 复用同一文件里已有的 `RequireAuth`（Task 3 不需要它）。

- [ ] **Step 1: 加 `RequireAuth` 组件**

编辑 `zg-tsp-web/src/router/index.tsx`，在 `Protected` 组件定义之后、`GuestOnly` 之前插入：

```tsx
/** 已登录守卫（不限角色、不套 AdminLayout）。
 *
 *  用于改密页这类独立全屏页：未登录跳登录页，已登录直接渲染。
 *  刻意不检查 must_change_password —— 该状态下用户本来就该停在这个页面上，
 *  若在这里也检查会形成重定向循环。 */
function RequireAuth({ children }: { children: ReactElement }): ReactElement {
  const { token, user, initialized } = useAuthStore()

  if (!initialized) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }
  if (!token || !user) return <Navigate to="/login" replace />

  return children
}
```

- [ ] **Step 2: 把改密路由挂到守卫下**

编辑 `zg-tsp-web/src/router/index.tsx`，把：

```tsx
      <Route path="/change-password" element={<ChangePasswordPage />} />
```

替换为：

```tsx
      <Route
        path="/change-password"
        element={
          <RequireAuth>
            <ChangePasswordPage />
          </RequireAuth>
        }
      />
```

- [ ] **Step 3: 类型检查 + 构建**

```bash
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-web
npm run build
```

Expected: `tsc -b` 无错误，Vite 构建成功，输出 `dist/`。若报 `ReactElement` 未导入，检查文件顶部 —— 现有 import 已有 `import type { ReactElement } from 'react'`，不要重复添加。

- [ ] **Step 4: 手工验证（可选，需服务端已启动）**

```bash
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-web
npm run dev -- --port 5174
```

浏览器打开 `http://localhost:5174/change-password`（未登录）→ 应跳到 `/login` 登录页。

- [ ] **Step 5: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add zg-tsp-web/src/router/index.tsx
git commit -m "$(cat <<'EOF'
Web：改密页加登录守卫 RequireAuth

/change-password 原为裸路由，游客可直接打开页面、提交才 401。
新增不限角色、不套 AdminLayout 的 RequireAuth 守卫，
未登录访问 /change-password 跳 /login。

刻意不检查 must_change_password：该状态下用户本就该停在改密页，
检查会形成重定向循环。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Web 端改密成功后回到来源页

现在改密成功后无条件 `navigate(ROLE_HOME[user.role], { replace: true })`，会把用户从「作业详情」等页面踢回角色首页。改成回到进入改密页时的来源页。

**Files:**
- Modify: `zg-tsp-web/src/pages/common/ChangePassword.tsx`
- Modify: `zg-tsp-web/src/components/AdminLayout.tsx`（下拉菜单入口传来源）
- Modify: `zg-tsp-web/src/pages/student/Profile.tsx`（「修改密码」按钮传来源）

**Interfaces:**
- Consumes: React Router 的 `useLocation()`（读 `location.state`）、`useNavigate()`。
- Produces: 路由 location state 的约定 `{ from: string }` —— 由入口写入、由改密页读取。Task 4（移动端）不涉及此约定。

- [ ] **Step 1: 改密页读取来源并跳转**

编辑 `zg-tsp-web/src/pages/common/ChangePassword.tsx`：

第 7 行改为：

```tsx
import { useLocation, useNavigate } from 'react-router-dom'
```

第 12 行附近，在 `const navigate = useNavigate()` 之后加：

```tsx
  const location = useLocation()
  // 入口通过 router state 传入来源页；无来源（如直接输 URL）时回退到角色首页
  const from = (location.state as { from?: string } | null)?.from
```

把 `onFinish` 里的跳转：

```tsx
      navigate(user ? ROLE_HOME[user.role] : '/login', { replace: true })
```

改为：

```tsx
      navigate(from ?? (user ? ROLE_HOME[user.role] : '/login'), { replace: true })
```

- [ ] **Step 2: AdminLayout 下拉入口传来源**

编辑 `zg-tsp-web/src/components/AdminLayout.tsx`：

确认顶部 import 已含 `useLocation`（现有代码第 77 行已在用 `location.pathname`，若缺失则改为
`import { useLocation, useNavigate } from 'react-router-dom'`）。

在下拉菜单项里，把：

```tsx
                  onClick: () => navigate('/change-password'),
```

改为：

```tsx
                  onClick: () =>
                    navigate('/change-password', { state: { from: location.pathname } }),
```

- [ ] **Step 3: 学生「我的」页按钮传来源**

编辑 `zg-tsp-web/src/pages/student/Profile.tsx`：

第 9 行改为：

```tsx
import { useLocation, useNavigate } from 'react-router-dom'
```

在 `const navigate = useNavigate()` 之后加：

```tsx
  const location = useLocation()
```

把第 59 行：

```tsx
        <Button onClick={() => navigate('/change-password')}>修改密码</Button>
```

改为：

```tsx
        <Button
          onClick={() => navigate('/change-password', { state: { from: location.pathname } })}
        >
          修改密码
        </Button>
```

- [ ] **Step 4: 类型检查 + 构建**

```bash
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-web
npm run build
```

Expected: 无类型错误，构建成功。

- [ ] **Step 5: 手工验证（需服务端已启动）**

```bash
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-web
npm run dev -- --port 5174
```

依次验证：

1. 以学生登录 → 进 `/student/homework` → 点开某个作业详情（`/student/homework/<id>`）→ 右上角头像 → 「修改密码」→ 填原密码+新密码 → 提交 → 应回到**作业详情页**，不是 `/student`
2. 右上角头像 →「修改密码」→ 提交 → 回 `/student`（从 `/student` 进来的，来源即 `/student`）
3. 管理员首登（`must_change_password=true`）→ 自动进 `/change-password` → 提交 → 应跳 `/admin`（强制模式无来源 state，`from` 为 undefined，回退 `ROLE_HOME`）

- [ ] **Step 6: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add zg-tsp-web/src/pages/common/ChangePassword.tsx \
        zg-tsp-web/src/components/AdminLayout.tsx \
        zg-tsp-web/src/pages/student/Profile.tsx
git commit -m "$(cat <<'EOF'
Web：改密成功后回到来源页而非强制跳角色首页

入口通过 router state 传 { from: pathname }（AdminLayout 下拉菜单、
学生「我的」页两处），改密页读取后回跳；无来源时回退到角色首页。
强制改密流程（must_change_password）行为不变。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 移动端改密页拆分到独立文件

`ChangePasswordPage` 现在定义在 `login_page.dart` 里（职责错位：登录页文件塞着改密页）。拆到 `lib/pages/common/change_password_page.dart`，Android/iOS 两份手工同步。

**Files:**
- Create: `zg-tsp-android/lib/pages/common/change_password_page.dart`
- Create: `zg-tsp-ios/lib/pages/common/change_password_page.dart`
- Modify: `zg-tsp-android/lib/pages/common/login_page.dart`（删掉 `ChangePasswordPage` 类定义）
- Modify: `zg-tsp-ios/lib/pages/common/login_page.dart`（同上）
- Modify: `zg-tsp-android/lib/main.dart`（改 import）
- Modify: `zg-tsp-ios/lib/main.dart`（同上）
- Modify: `zg-tsp-android/lib/pages/common/profile_page.dart`（改 import）
- Modify: `zg-tsp-ios/lib/pages/common/profile_page.dart`（同上）

**Interfaces:**
- Consumes: `AuthApi.instance.changePassword(String oldPassword, String newPassword)`（`lib/core/apis.dart:53`）、`AuthState.markPasswordChanged()`、`errorMessage(Object e)`（`lib/core/api_client.dart:137`）、`showSnack(BuildContext, String, {bool error})`（`lib/widgets/common.dart`）。
- Produces: `class ChangePasswordPage extends StatefulWidget`，构造参数 `const ChangePasswordPage({super.key, this.forced = false})`，字段 `final bool forced`。**签名与行为完全不变**，只是换了文件位置。

- [ ] **Step 1: 新建 Android 端改密页文件**

创建 `zg-tsp-android/lib/pages/common/change_password_page.dart`，内容为把 `login_page.dart` 第 279-394 行（`class ChangePasswordPage` 起到文件末尾）**原样搬过来**，并在文件头加上独立注释：

```dart
/// 修改密码页（PRD 5.1、9 公共）。
///
/// 从 login_page.dart 拆出：登录页文件不应承载改密页。
/// - forced=true：admin 首登强制改密，RootGate 直接把它作为 home 内容；
///   改密成功后由 AuthState.markPasswordChanged() 通知 RootGate 自动分流，本页不跳转。
/// - forced=false：从「我的」页进入，改密成功后 pop 回来源页。
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../state/auth_state.dart';
import '../../widgets/common.dart';

class ChangePasswordPage extends StatefulWidget {
  const ChangePasswordPage({super.key, this.forced = false});

  /// true 时为 admin 首登强制改密（PRD 5.1）
  final bool forced;

  @override
  State<ChangePasswordPage> createState() => _ChangePasswordPageState();
}

class _ChangePasswordPageState extends State<ChangePasswordPage> {
  final _formKey = GlobalKey<FormState>();
  final _old = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _old.dispose();
    _new.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _submitting = true);
    try {
      await AuthApi.instance.changePassword(_old.text, _new.text);
      if (!mounted) return;
      await context.read<AuthState>().markPasswordChanged();
      if (!mounted) return;
      showSnack(context, '密码修改成功');
      if (widget.forced) {
        // 强制改密场景下本页就是 RootGate 的 home 内容，markPasswordChanged()
        // 已 notifyListeners，RootGate 会自动切到对应角色的首页，无需跳转。
      } else {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.forced ? '首次登录，请修改密码' : '修改密码'),
        automaticallyImplyLeading: !widget.forced,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (widget.forced) ...[
                  Card(
                    color: Colors.orange.shade50,
                    child: const Padding(
                      padding: EdgeInsets.all(12),
                      child: Text('使用初始密码登录后必须修改密码，修改前无法使用其他功能。'),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                TextFormField(
                  controller: _old,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '原密码',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) => (v == null || v.isEmpty) ? '请输入原密码' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _new,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '新密码（至少 6 位）',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) =>
                      (v == null || v.length < 6) ? '密码至少 6 位' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _confirm,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '确认新密码',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) =>
                      v != _new.text ? '两次输入的密码不一致' : null,
                ),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _submitting ? null : _submit,
                  child: const Text('确认修改'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: 从 login_page.dart 删除该类并改文件头注释**

编辑 `zg-tsp-android/lib/pages/common/login_page.dart`：

- 删除 `class ChangePasswordPage` 起到文件末尾的整段（当前第 279-394 行）
- 文件头第 1 行 `/// 登录 / 注册 / 修改密码页（PRD 5.1、9 公共）。` 改为：

```dart
/// 登录 / 注册页（PRD 5.1、9 公共）。
```

- `login_page.dart` **不需要** import `change_password_page.dart`（它不引用该类）。删除类后 `login_page.dart` 的现有 import **全部仍在使用**，无需增删：`AuthState`（第 34、48 行）、`showSnack`（第 42、187、190 行）、`errorMessage`（第 42、190 行，来自 `core/api_client.dart`）、`AuthApi`（第 177 行，来自 `core/apis.dart`）、`provider`（`context.read` / `context.watch`）、`flutter/material.dart`。

- [ ] **Step 3: 改 main.dart 与 profile_page.dart 的 import**

`zg-tsp-android/lib/main.dart`：

```dart
import 'core/config.dart';
import 'pages/admin/admin_home.dart';
import 'pages/common/change_password_page.dart';
import 'pages/common/login_page.dart';
import 'pages/parent/parent_home.dart';
```

（`main.dart` 第 75 行 `return const ChangePasswordPage(forced: true);` 保持不变，靠新 import 解析。）

`zg-tsp-android/lib/pages/common/profile_page.dart`：

第 9 行 `import 'login_page.dart';` 改为 `import 'change_password_page.dart';`

（该文件仅为了 `ChangePasswordPage` 才 import `login_page.dart`，改完就不再依赖登录页。）

- [ ] **Step 4: 同步到 iOS 端**

把 Android 端这 4 个文件的改动**逐一手工复制**到 iOS 端对应路径：

- `zg-tsp-ios/lib/pages/common/change_password_page.dart`（新建，内容与 Android 版**逐字节相同**）
- `zg-tsp-ios/lib/pages/common/login_page.dart`（同样删类、改文件头注释）
- `zg-tsp-ios/lib/main.dart`（同样加 import）
- `zg-tsp-ios/lib/pages/common/profile_page.dart`（同样改 import）

iOS 的 `main.dart` **首行注释保持自己的工程名** `/// zg-tsp-ios 应用入口（P8）。`，不要照抄 Android 的。

- [ ] **Step 5: 静态分析**

```bash
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-android && flutter analyze
cd /Users/zg/PycharmProjects/zg-tsp/zg-tsp-ios     && flutter analyze
```

Expected: 两端均 `No issues found!`。若报 `unused_import`，按提示删掉多余 import。

- [ ] **Step 6: 验证两端同步**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
diff zg-tsp-android/lib/pages/common/change_password_page.dart \
     zg-tsp-ios/lib/pages/common/change_password_page.dart && echo "改密页两端一致"
diff zg-tsp-android/lib/pages/common/login_page.dart \
     zg-tsp-ios/lib/pages/common/login_page.dart && echo "登录页两端一致"
diff zg-tsp-android/lib/pages/common/profile_page.dart \
     zg-tsp-ios/lib/pages/common/profile_page.dart && echo "我的页两端一致"
```

Expected: 三条 `diff` 均无输出差异（`profile_page.dart` 与 `login_page.dart` 当前本就两端逐字节相同，改动后仍应相同）。

- [ ] **Step 7: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add zg-tsp-android/lib/pages/common/change_password_page.dart \
        zg-tsp-ios/lib/pages/common/change_password_page.dart \
        zg-tsp-android/lib/pages/common/login_page.dart \
        zg-tsp-ios/lib/pages/common/login_page.dart \
        zg-tsp-android/lib/main.dart \
        zg-tsp-ios/lib/main.dart \
        zg-tsp-android/lib/pages/common/profile_page.dart \
        zg-tsp-ios/lib/pages/common/profile_page.dart
git commit -m "$(cat <<'EOF'
移动端：改密页从 login_page.dart 拆到独立文件（两端同步）

ChangePasswordPage 原先定义在登录页文件里，职责错位。
拆到 lib/pages/common/change_password_page.dart，
login_page.dart / main.dart / profile_page.dart 改 import。
类签名与行为不变，Android 与 iOS 两份手工同步。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: dev.sh 启动前输出代码来源与新鲜度报告

`dev.sh` 的 `REPOS_DIR` 默认命中落后的独立仓库，对"跑的是哪份代码"没有任何提示 —— 这正是本轮问题的根因。加一份启动前报告。

**Files:**
- Modify: `scripts/dev.sh`（新增 4 个函数 + 改 `find_repos_dir` + 主流程加调用）

**Interfaces:**
- Consumes: `ROOT`（脚本自身所在仓库根）、`REPOS_DIR`（最终解析出的代码目录）。
- Produces: 三个新函数 `find_repos_dir`（改签名，改为设置全局变量）、`report_source`、`report_module_git`、`count_diff_files`；两个新全局变量 `REPOS_DIR_ENV`（原始环境变量值）、`REPOS_SOURCE`（命中来源描述）。

- [ ] **Step 1: 改 `find_repos_dir` 以记录命中来源**

当前实现用命令替换 `REPOS_DIR="$(find_repos_dir || true)"` 接收结果 —— 命令替换在子 shell 里执行，子 shell 的变量赋值不会传回父 shell，所以来源信息必须在函数里写全局变量。

编辑 `scripts/dev.sh`，把第 36-64 行整块替换为：

```sh
# --- 定位仓库目录 ---
# POSIX sh 没有数组，改用换行分隔的字符串逐行遍历。
#
# 注意：REPOS_DIR 的原始环境变量值单独存到 REPOS_DIR_ENV。
# 本函数直接写全局变量 REPOS_DIR / REPOS_SOURCE 而非返回值 ——
# 调用方若用命令替换接收，子 shell 里的赋值会丢失，拿不到来源信息。
REPOS_DIR_ENV="${REPOS_DIR:-}"
REPOS_DIR=""
REPOS_SOURCE=""

find_repos_dir() {
  local candidates
  candidates=$(printf '%s\n' \
    "${REPOS_DIR_ENV}" \
    "${ROOT}/../zg-tsp-repos" \
    "${ROOT}" \
    "${HOME}/zg-tsp-repos"
  )
  local d
  # 用 while read 而非 for 词分割，避免路径含空格时被拆开。
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    if [ -d "$d/zg-tsp-server" ] && [ -d "$d/zg-tsp-web" ]; then
      REPOS_DIR="$(cd "$d" && pwd)"
      case "$d" in
        "${ROOT}/../zg-tsp-repos") REPOS_SOURCE="默认探测 ../zg-tsp-repos" ;;
        "${ROOT}")               REPOS_SOURCE="默认探测 本快照 \$ROOT" ;;
        "${HOME}/zg-tsp-repos")  REPOS_SOURCE="默认探测 ~/zg-tsp-repos" ;;
        *)                       REPOS_SOURCE="环境变量 REPOS_DIR" ;;
      esac
      return 0
    fi
  done <<EOF
${candidates}
EOF
  return 1
}
```

并把原第 58-64 行：

```sh
REPOS_DIR="$(find_repos_dir || true)"
if [ -z "$REPOS_DIR" ]; then
```

改为：

```sh
find_repos_dir || true
if [ -z "$REPOS_DIR" ]; then
```

（`REPOS_DIR` 现在由函数直接赋值，`|| true` 吞掉"没找到"的返回码。）

- [ ] **Step 2: 新增报告函数**

在 `scripts/dev.sh` 的 `# --- 工具函数 ---` 段之后、`# --- 启动各模块 ---` 之前插入：

```sh
# --- 代码来源与新鲜度报告 ---

# 统计差异时排除的路径（依赖 / 构建产物 / 缓存 / .gitignore 排除项）。
# -x 按条目名匹配，对目录同样生效。
diff_exclude_args() {
  for x in .git node_modules dist build .dart_tool .gradle .venv \
           __pycache__ .dev-logs .pytest_cache .idea .DS_Store \
           tests data uploads Pods .symlinks DerivedData \
           .env .env.local pubspec.lock local.properties key.properties \
           Dev.xcconfig Prod.xcconfig; do
    printf -- '-x %s ' "$x"
  done
}

# 统计两个目录之间的差异文件数（0 表示一致或不存在）。
count_diff_files() {
  local a="$1" b="$2" n
  [ -d "$a" ] && [ -d "$b" ] || { echo 0; return 0; }
  # shellcheck disable=SC2086
  n=$(diff -rq "$a" "$b" $(diff_exclude_args) 2>/dev/null | grep -c . || true)
  [ -n "$n" ] || n=0
  echo "$n"
}

# 打印单个模块的 git 状态。
report_module_git() {
  local name="$1" dir="$2" branch head tracked untracked
  if [ ! -d "$dir" ]; then
    printf '    %-16s %s\n' "$name" "（目录不存在）"
    return 0
  fi
  if ! git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf '    %-16s %s\n' "$name" "（非 git 目录）"
    return 0
  fi
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "-")
  head=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "-")
  # grep -c 在无匹配时退出码为 1，用 || true 兜住（set -eu 下会直接退出脚本）
  tracked=$(git -C "$dir" status --porcelain 2>/dev/null | grep -v '^??' | grep -c . || true)
  untracked=$(git -C "$dir" status --porcelain 2>/dev/null | grep '^??' | grep -c . || true)
  [ -n "$tracked" ] || tracked=0
  [ -n "$untracked" ] || untracked=0
  if [ "$tracked" = "0" ] && [ "$untracked" = "0" ]; then
    printf '    %-16s %-8s %-10s %s\n' "$name" "$branch" "$head" "干净"
  else
    printf '    %-16s %-8s %-10s %s\n' "$name" "$branch" "$head" \
      "${tracked} 个已跟踪改动 / ${untracked} 个未跟踪"
  fi
}

# 打印整体报告。$1=full 时额外统计与本快照的差异文件数。
report_source() {
  local mode="${1:-short}" m n total=0
  echo
  info "代码来源与新鲜度"
  printf '  REPOS_DIR = %s\n' "${REPOS_DIR}"
  printf '  命中来源 = %s\n' "${REPOS_SOURCE:-未知}"
  if [ "${REPOS_DIR}" != "${ROOT}" ]; then
    warn "当前跑的是独立仓库，与本快照 ${ROOT} 不同步"
    warn "改动请确认落在哪一份；构建本快照请显式指定 REPOS_DIR=\"\$PWD\""
  else
    ok "当前跑的就是本快照"
  fi

  echo "  模块 git 状态："
  for m in zg-tsp-server zg-tsp-web zg-tsp-android zg-tsp-ios zg-tsp-docs; do
    report_module_git "$m" "${REPOS_DIR}/${m}"
  done

  if [ "$mode" = "full" ] && [ "${REPOS_DIR}" != "${ROOT}" ]; then
    echo "  与本快照的差异："
    for m in zg-tsp-server zg-tsp-web zg-tsp-android zg-tsp-ios zg-tsp-docs; do
      n=$(count_diff_files "${ROOT}/${m}" "${REPOS_DIR}/${m}")
      total=$((total + n))
      printf '    %-16s %s 处\n' "$m" "$n"
    done
    if [ "$total" -eq 0 ]; then
      ok "与本快照完全一致"
    else
      warn "与本快照有 ${total} 处差异"
    fi
  fi
}
```

- [ ] **Step 3: 在主流程调用报告**

编辑 `scripts/dev.sh` 的主流程段（`CMD="${1:-start}"` 之后、`case` 之前）插入：

```sh
# 启动类命令打完整报告（含与快照差异），status 打简版。
# stop / logs 不打印 —— 它们不启动任何模块，输出会变成噪音。
case "${CMD}" in
  start|server|web|ios|android|all|"")
    report_source full
    ;;
  status)
    report_source short
    ;;
esac
```

注意这段 `case` 必须在已有的 `case "${CMD}" in ... esac` **之前**，且原有的 `CMD="${1:-start}"` 定义要在这段之前。

- [ ] **Step 4: 验证脚本语法与输出**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
sh -n scripts/dev.sh && echo "语法 OK"
```

Expected: `语法 OK`（`sh -n` 只做语法检查不执行）。

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/dev.sh status
```

Expected: 报告里出现 `REPOS_DIR = /Users/zg/PycharmProjects/zg-tsp-repos`（默认探测独立仓库，因为 `../zg-tsp-repos` 存在）、`命中来源 = 默认探测 ../zg-tsp-repos`、黄色警告「当前跑的是独立仓库，与本快照 ... 不同步」，以及五个模块的 git 状态行。

再验证本快照路径：

```bash
cd /Users/zg/PycharmProjects/zg-tsp
REPOS_DIR="$PWD" ./scripts/dev.sh status
```

Expected: `REPOS_DIR = /Users/zg/PycharmProjects/zg-tsp`、`命中来源 = 环境变量 REPOS_DIR`、`✓ 当前跑的就是本快照`。

再验证 full 模式的差异统计：

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/dev.sh status   # short 模式，不含差异
```

用 `start` 类命令验证 full 模式（**会真的启动服务端与 Web 端**）：

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/dev.sh web
```

Expected: 报告里出现「与本快照的差异：」段落，五个模块各自列出**非零**差异处数（此时本快照已领先独立仓库，server / web / android / ios / docs 都应有非零值）。差异统计已排除 `.gitignore` 排除项与构建产物，所以数出来的是**源码**差异。看完后 `./scripts/dev.sh stop` 停掉。

- [ ] **Step 5: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add scripts/dev.sh
git commit -m "$(cat <<'EOF'
dev.sh：启动前输出代码来源与新鲜度报告

REPOS_DIR 探测顺序是 ../zg-tsp-repos → $ROOT → ~/zg-tsp-repos，
默认命中独立仓库，脚本此前对「跑的是哪份代码」毫无提示 ——
本轮 Web 端看不到改密入口正是这个坑造成的。

新增报告：REPOS_DIR 路径与命中来源、与本快照是否同步的警告、
五个模块的分支/HEAD/脏文件计数，full 模式再统计与本快照的差异文件数。
find_repos_dir 改为写全局变量（原命令替换会丢掉子 shell 里的赋值）。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 文档同步

**Files:**
- Modify: `zg-tsp-docs/sys_doc/PRD.md`（第 28 行迭代条目 11）
- Modify: `zg-tsp-docs/sys_doc/迭代.md`（第 15 行）
- Modify: `docs/superpowers/specs/2026-10-30-self-service-password-change-design.md`（修正 §4.1 的事实错误）

**Interfaces:**
- Consumes: 无（纯文档）。
- Produces: 无代码接口。

- [ ] **Step 1: 修正 spec §4.1 的事实错误**

`docs/superpowers/specs/2026-10-30-self-service-password-change-design.md` 的 §4.1「服务端：密码强度校验」写的是服务端**尚未**校验。实际 `zg-tsp-server/app/schemas/auth.py:50` 已有 `min_length=6`，且 `app/main.py:86` 的 `RequestValidationError` 处理器已转成 400。

把 §4.1 整节替换为：

```markdown
### 4.1 服务端：密码强度校验（**已满足，本轮只补验收覆盖**）

**核实结论**：`zg-tsp-server/app/schemas/auth.py` 的 `ChangePasswordRequest.new_password`
**已经**声明 `Field(..., min_length=6, max_length=64)`；`zg-tsp-server/app/main.py` 的
`RequestValidationError` 全局处理器把 Pydantic 校验失败转成 **400 + `{code, message}`**
（不是 FastAPI 默认的 422），符合项目统一响应契约。

`zg-tsp-server/app/routers/auth.py` 的 `change_password` 也已有原密码校验与
"新旧密码不得相同"校验。

因此服务端**不需要改代码**。本轮改为在 `acceptance_check.py` 补第 18 组端到端断言，
把这三条契约钉住（见 §4.5）。
```

同时更新同节 §4.4 的排除清单 —— 实施时 `diff_exclude_args` 除构建产物外，还需排除
`.gitignore` 排除项（`tests/`、`app/data/`、`app/uploads/`、`.env`、`pubspec.lock`、
`ios/Pods/` 等），否则差异统计会失真：

- [ ] **Step 2: 更新 PRD.md 迭代条目**

`zg-tsp-docs/sys_doc/PRD.md` 第 28 行当前是：

```
| 11 | 登录后可自助修改当前账户密码 | `POST /auth/change-password` 已实现；本迭代在 Web（右上角菜单 / 学生端「我的」页）与移动端补充入口 |
```

改为：

```
| 11 | 登录后可自助修改当前账户密码 | ✅ 已完成。`POST /auth/change-password` 服务端契约已满足（新密码 ≥6 位，校验失败返回 400）；Web 端入口在右上角头像菜单与学生端「我的」页，移动端入口在四角色通用「我的」页；验收见 `scripts/acceptance_check.py` 第 18 组断言 |
```

- [ ] **Step 3: 更新迭代.md**

`zg-tsp-docs/sys_doc/迭代.md` 第 15 行当前是：

```
- 登录之后可以自助修改当前账户密码
```

改为：

```
- 登录之后可以自助修改当前账户密码 ✅（服务端契约已满足；Web 端右上角菜单 / 学生端「我的」页，移动端四角色「我的」页）
```

- [ ] **Step 4: 提交**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git add zg-tsp-docs/sys_doc/PRD.md zg-tsp-docs/sys_doc/迭代.md \
        docs/superpowers/specs/2026-10-30-self-service-password-change-design.md
git commit -m "$(cat <<'EOF'
文档：勾选「登录后可自助修改当前账户密码」迭代条目

PRD.md 第 28 行、迭代.md 第 15 行标记完成并写明入口位置。
同时修正 spec §4.1 的事实错误：服务端 ChangePasswordRequest 本就
有 min_length=6，全局 RequestValidationError 处理器已转 400，
本轮只补验收覆盖，不改服务端代码。

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 全量同步独立仓库并复验

本快照是五个独立仓库的**权威源头**。独立仓库当前是快照的严格子集（源码层面无任何独占文件，已逐文件核对），需要重建并复验。

**Files:**
- 操作对象: `../zg-tsp-repos/`（五个独立仓库，由 `scripts/split_repos.sh split` 重建）
- 无源码改动

**Interfaces:**
- Consumes: `scripts/split_repos.sh`（`split` / `push` / `status` 子命令）、`zg-tsp-server/app/seed/migrate_v21.py`。
- Produces: `../zg-tsp-repos/` 下五个与本快照源码一致的仓库；`split/<模块>` 本地分支。

**⚠️ 不可逆操作提醒**：`split` 会对 `../zg-tsp-repos/<模块>` 执行 `rm -rf` 后重建。执行前必须完成 Task 1-6 的全部 commit。

- [ ] **Step 1: 确认本快照工作区干净、提交齐全**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
git status --short
git log --oneline -8
```

Expected: `git status --short` **只**剩未跟踪的 `docs/superpowers/plans/`（上一轮迭代的计划文档，与本轮无关，可不动）。若还有已跟踪文件的改动，先提交。

- [ ] **Step 2: 复核独立仓库不会丢失源码**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
for m in zg-tsp-server zg-tsp-web zg-tsp-android zg-tsp-ios zg-tsp-docs; do
  echo "--- $m ---"
  diff -rq "$m" "../zg-tsp-repos/$m" -x .git -x node_modules -x dist \
      -x build -x .dart_tool -x .gradle -x .venv -x __pycache__ \
      -x .dev-logs 2>/dev/null | grep -E "^Only in \.\./" | head -20
done
```

Expected: **每个模块都没有输出**（没有 `Only in ../zg-tsp-repos/...` 的行）。任何一行都意味着独立仓库有快照没有的源码，必须先处理（拷回快照）再继续。

（注意：`diff` 报的 `Only in zg-tsp-...`（快照侧独有）是**预期的** —— `tests/`、`app/data/`、`app/uploads/*`、`.env`、`pubspec.lock` 等被 `.gitignore` 排除，只存在于快照工作区。只有 `../zg-tsp-repos/` 侧的 `Only in` 才是真问题。）

- [ ] **Step 3: 重建独立仓库**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/split_repos.sh split
```

Expected: 每个模块输出一行 `✓ N 次提交`，最后输出「完成。各仓库位于 /Users/zg/PycharmProjects/zg-tsp-repos」。该脚本会生成 `split/<模块>` 分支（本地）。

- [ ] **Step 4: 校验重建结果与快照一致**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
for m in zg-tsp-server zg-tsp-web zg-tsp-android zg-tsp-ios zg-tsp-docs; do
  echo "--- $m ---"
  diff -rq "$m" "../zg-tsp-repos/$m" -x .git -x node_modules -x dist \
      -x build -x .dart_tool -x .gradle -x .venv -x __pycache__ \
      -x .dev-logs 2>/dev/null | head -10
done
```

Expected: 各模块的差异**只出现在被 `.gitignore` 排除的路径上**，即只可能是这些 `Only in zg-tsp-<模块>` 行：

| 路径 | 所属模块 | 排除原因 |
|------|---------|---------|
| `tests/` | server | 根与模块 `.gitignore` 均排除，测试是本地联调资产 |
| `app/data/` | server | 模块 `.gitignore` 排除 |
| `app/uploads/*`（除 `.gitkeep`） | server | 模块 `.gitignore` 排除，含运行时上传的文章附件 |
| `.env` | server | 模块 `.gitignore` 排除，含真实密钥 |
| `pubspec.lock` | android / ios | 模块 `.gitignore` 排除 |
| `node_modules/`、`dist/` | web | 模块 `.gitignore` 排除 |
| `.dart_tool/`、`build/`、`android/.gradle/`、`android/local.properties`、`android/key.properties` | android | 模块 `.gitignore` 排除 |
| `ios/Flutter/{Dev,Prod}.xcconfig`、`ios/Pods/` 等 | ios | 模块 `.gitignore` 排除 |

**除上述之外不应有任何差异行。** 若出现别的差异（例如某个 `.py`、`.tsx`、`.dart` 文件报 `differ`），说明 split 出了问题，停下来排查。

由于 `app/uploads/` 里的附件会在重建后消失（只在 git 里有 `.gitkeep`），若本地开发库里有依赖这些附件的数据，用 `python -m app.seed.initial_data` 重新生成种子数据即可。

- [ ] **Step 5: 独立仓库服务端数据迁移**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-server
cp .env.example .env 2>/dev/null || true
# 按需改 .env 的 DATABASE_URL / JWT_SECRET
python -m app.seed.initial_data
python -m app.seed.migrate_v21
```

Expected: `migrate_v21` 输出三行「跳过（已存在）：file_url / file_name / file_type」或「已添加：xxx」—— 脚本幂等，两种输出都正常。

- [ ] **Step 6: 独立仓库复验**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/zgtsp-server-repos.log 2>&1 &
sleep 4
curl -s -X POST http://127.0.0.1:8000/health
cd /Users/zg/PycharmProjects/zg-tsp-repos
python zg-tsp-docs/scripts/acceptance_check.py
```

Expected: health 返回 `{"code":0,...}`；验收脚本末尾 `=== 业务验收：N/M 通过 ===`，第 18 组断言全 ✅。

- [ ] **Step 7: 独立仓库构建验证**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-web
npm install
npm run build
```

Expected: `tsc -b` 无错误，Vite 构建成功。

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-android && flutter analyze
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-ios     && flutter analyze
```

Expected: 两端 `No issues found!`。

- [ ] **Step 8: 用新的 dev.sh 报告确认两边已同步**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/dev.sh status
```

Expected: 差异统计段落全部为 `0 处`，并输出 `✓ 与本快照完全一致`。

（`diff_exclude_args` 已排除 `tests/`、`app/data/`、`app/uploads/`、`.env`、`pubspec.lock` 等 `.gitignore` 项与构建产物，所以同步后源码差异应为 0。若某模块非 0，说明该模块有源码没同步过去。）

- [ ] **Step 9: 停掉服务并记录状态**

```bash
cd /Users/zg/PycharmProjects/zg-tsp
./scripts/dev.sh stop
```

若 Task 1 步骤 3 起了后台 uvicorn，一并停掉：

```bash
pkill -f "uvicorn app.main:app" || true
```

---

## 完成判定

- [ ] `python zg-tsp-docs/scripts/acceptance_check.py` 全绿，第 18 组 7 条断言通过
- [ ] `cd zg-tsp-web && npm run build` 通过
- [ ] `cd zg-tsp-android && flutter analyze` 与 `cd zg-tsp-ios && flutter analyze` 均 `No issues found!`
- [ ] `sh -n scripts/dev.sh` 通过；`./scripts/dev.sh status` 正确报告来源与差异
- [ ] `../zg-tsp-repos/` 五个仓库与本快照源码一致，`acceptance_check.py` 在独立仓库同样全绿
- [ ] PRD.md 第 28 行与迭代.md 第 15 行已勾选
