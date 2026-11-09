# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库形态

本项目分为五个独立仓库，不是一个可整体构建的单体。**当前聚合检出只有 server、web、docs；Android 和 iOS 目录不在本检出中**。本机的移动端独立仓库位于 `../zg-tsp-repos/`，其他环境需先确认其位置。下表描述完整工作区，而非保证所有目录都在当前检出：

| 目录 | 内容 | 技术栈 |
|------|------|--------|
| `zg-tsp-server/` | 服务端 | Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 |
| `zg-tsp-web/` | Web 管理端 | React 18 / Vite 6 / Ant Design 5 / Zustand 5 |
| `zg-tsp-android/` `zg-tsp-ios/` | 移动端 | Flutter 3.47 / Dart 3.13（Provider，非 go_router） |
| `zg-tsp-docs/` | **契约与验收**（PRD、config、ENV_SETUP、验收脚本） | Markdown / Python |

**需求与 API 契约的权威来源是 `zg-tsp-docs/sys_doc/PRD.md`**（v2.1）。它同时承担了 PRD、API 契约、数据库建表 SQL、权限矩阵、验收清单五重角色。改接口前先读它；改完后要同步 `zg-tsp-web/src/api/types.ts` 和 `zg-tsp-*/lib/core/models.dart`（这两份是 PRD 的手工副本，无自动生成）。

### 三个必须知道的结构性事实

1. **Flutter 两端的 `lib/` 是物理复制的两份**，位于独立的 Android、iOS 仓库，而不是当前聚合检出。两端代码基本相同，**改任何一份都必须检查并手工同步另一份**。

2. **`scripts/dev.sh` 启动的不一定是本目录的代码**。有效的 `REPOS_DIR` 优先；否则探测 `../zg-tsp-repos` → `$ROOT` → `~/zg-tsp-repos`。若命中独立仓库，其代码可能与本检出不同步；改完代码后确认运行的是哪一份。

3. **PRD 里的建表 SQL 是 SQLite 方言**，而服务端实际跑 MySQL 8。库表结构以 `zg-tsp-server/app/models/entities.py`（15 张表）为准，PRD 第 4.1 节仅作参考。

## 常用命令

### 服务端

```bash
cd zg-tsp-server
pip install -r requirements.txt
cp .env.example .env            # 按需改 DATABASE_URL / JWT_SECRET

python -m app.seed.initial_data        # 建表 + 种子（幂等）
python -m app.seed.initial_data --reset # 删表重建（危险）
python -m app.seed.apply_comments      # 给已有表补字段中文 COMMENT

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`.env` 路径基于 `app/config.py` 向上两级，不依赖 CWD；环境变量优先级高于 `.env`。

**部署用数据库初始化（顶层脚本，不进服务端 venv）**：

```bash
./scripts/init.sh            # 建库 + 建表 + 积分规则 + admin（幂等）
./scripts/init.sh --drop     # 先删库重建（危险，需二次确认）
```

它导入 `zg-tsp-docs/sql/init.sql` —— 该文件由 `python -m app.seed.export_ddl` **从 ORM 生成**（改了 `app/models/entities.py` 要重新生成）。admin 密码以 `__ADMIN_BCRYPT_HASH__` 占位符写入，由脚本运行时替换成 bcrypt 哈希；**直接 `mysql < init.sql` 会导致 admin 无法登录**。

**健康检查是 POST，不是 GET**：`curl -X POST http://127.0.0.1:8000/health` 返回统一响应，`data` 含 `status` 和当前 `env`。浏览器直接打开会 405（CORS `allow_methods` 只放行 `POST, OPTIONS`）。

测试（**需要可连的 MySQL**，不 mock、不用 sqlite）：

```bash
pytest                          # 全部
pytest tests/test_auth.py       # 单文件
pytest tests/test_auth.py::test_login_success   # 单用例
pytest -k "login" -x -vv
```

测试使用配置的真实 MySQL，会提交数据并调用包括删除在内的业务接口，可能留下数据；**使用专用隔离数据库，不要假定测试只插入或更新**。例如 `DATABASE_URL=mysql+pymysql://.../zg_tsp_other pytest`。`tests/` 被 gitignore，干净检出可能没有测试文件。清理工具有破坏性，先查看 `python -m app.utils.purge_test_data --dry-run` 的结果并确认目标数据库。

### Web 端

```bash
cd zg-tsp-web
npm install        # Node >=20
npm run dev        # vite --mode development，端口 5173
npm run build      # = tsc -b && vite build --mode production（含类型检查）
npm run build:dev
npm run preview
```

**`npm run lint` 当前必然失败**——脚本存在但仓库里没有任何 ESLint 配置文件（无 `.eslintrc*` / `eslint.config.*`）。要修需补 ESLint 8 的 eslintrc 格式配置。Prettier 完全没有，格式化靠手写。

### 移动端

```bash
cd ../zg-tsp-repos/zg-tsp-android   # 或同级的 zg-tsp-ios；按实际独立仓库位置调整
flutter pub get
flutter analyze     # analysis_options.yaml 是 flutter_lints 默认值，零自定义规则
flutter test        # 仅 test/config_test.dart，6 个离线用例，无 widget/API 测试
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android 模拟器用 10.0.2.2
```

打包**必须走 `scripts/build.sh`**，它会先做环境预检并自动注入渠道配置：

```bash
# 从聚合仓库根目录执行；按实际独立仓库位置调整 REPOS_DIR
REPOS_DIR="$PWD/../zg-tsp-repos" ./scripts/build.sh android dev --check
REPOS_DIR="$PWD/../zg-tsp-repos" ./scripts/build.sh android dev   # → APK
REPOS_DIR="$PWD/../zg-tsp-repos" ./scripts/build.sh android prod  # → AAB
REPOS_DIR="$PWD/../zg-tsp-repos" ./scripts/build.sh ios dev       # → IPA
```

构建前确认 `REPOS_DIR` 所指目录确实包含目标移动端；当前聚合检出没有移动端，不能用 `REPOS_DIR="$PWD"` 构建。预检需带平台参数。iOS 签名团队可通过 `DEVELOPMENT_TEAM=<你的 Team ID>` 指定。`build.sh` 默认 dev API 为 `127.0.0.1`、prod 为占位域名 `https://api.example.com`；设置 `API_BASE_URL` 为设备可访问的地址。`dev.sh` 则使用 `API_TARGET`，Android 模拟器访问宿主机通常用 `10.0.2.2`。

### 顶层运维脚本

```bash
./scripts/dev.sh start|server|web|ios|android|all|stop|status|logs
./scripts/split_repos.sh split|push|status     # subtree 拆分为 5 个独立仓库
```

`dev.sh` 是 POSIX `sh`（**不能用数组、`[[ ]]`、进程替换**），日志与 PID 落在 `.dev-logs/`。`build.sh` 是 bash 3.2 兼容。**`split_repos.sh split` 会删除已有目标目录后重建；`dev.sh stop` 可能终止占用配置端口的其他进程。**执行前确认目标及影响。`init.sh` 也会自动探测仓库位置，执行前确认 SQL 和数据库来源。

### 验收

```bash
ACCEPTANCE_ADMIN_PASSWORD='<admin密码>' python zg-tsp-docs/scripts/acceptance_check.py  # 需服务端已启动
python zg-tsp-docs/scripts/independence_check.py   # 模块独立性静态检查，无需运行时
```

`acceptance_check.py` 硬编码 `http://127.0.0.1:8000`，需要管理员密码，会通过真实接口产生持久测试数据并修改积分规则。独立性检查要求五个模块目录同级；当前聚合检出缺少移动端，不能假定该检查完整通过。

## 服务端架构

```
routers → services → db/repo.py → models/entities.py
routers → schemas/（仅 auth、admin 有独立文件，其余 Pydantic 模型内联在 router 里）
```

目录是 `app/routers/`、`app/config.py`、`app/db/`、`app/utils/`——**没有 `app/core/` 或 `app/api/`**。

### 全 POST + 统一响应

业务接口通常使用 `POST` + JSON Body，参数不进 URL；作业提交和文章文件上传使用 multipart 表单。`/uploads` 静态文件通过 GET 提供，挂载本身没有鉴权依赖。业务响应为 `{code, message, data}`，分页数据在 `data` 里嵌 `{list, total, page, size}`。

`app/utils/response.py` 提供 `ok()` / `fail()`；`app/main.py` 注册三个全局异常处理器。**router 里抛 `HTTPException` 时 `detail` 必须是 `{"code": ..., "message": ...}` 字典**，否则 handler 会退化成 `fail(status_code, str(detail))`。各 router 文件顶部自带一份 `_bad_request/_forbidden/_not_found` 私有 helper 来保证这个形状。

### 鉴权：无中间件，全靠依赖

`app/utils/deps.py` 是唯一鉴权入口，四个依赖：

- `get_current_user` — 解析 `Bearer` token，**每次请求都查库**（所以后台禁用用户后已签发的 JWT 立即生效，不能加缓存）
- `get_verified_user` — 额外拦截 `must_change_password` 的 admin
- `require_roles(*roles)` / `require_admin` — 角色工厂

JWT payload 只有 `user_id/role/exp`，**role 在 payload 里但从不用于判断**——实际角色一律回库读 `user.role`。

角色控制分三级：

1. **路由级**：admin 组用 `APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])` 整组锁死。
2. **函数级**：teacher/student/parent 路由用 `get_verified_user` 后在函数体第一行判断角色（每个 router 各自定义 `_require_teacher` 等私有 helper）。
3. **数据级**：防越权的关键，每个 router 各写一份，如 `_own_class_or_403`（校验 `klass.teacher_id != user.id`）、`_own_child`（校验 `parent_students` 关系）。admin 账号不可被任何 admin 操作（`_protect_admin`）。

注册只开放 student/teacher/parent（`REGISTERABLE_ROLES`）；teacher 注册必须带有效邀请码，**一码一用**。

### 数据层

`app/db/repo.py` 是共享数据访问层，但并非唯一入口：router 和 service 也直接使用 SQLAlchemy session。事务通常由 router 提交，Repo 通常负责 add/flush 而不 commit；没有 Unit of Work。积分操作依赖学生行锁及锁定读来控制并发，修改时保留这些语义。

`app/db/session.py`：`pool_pre_ping=True` + `pool_recycle=3600`（应对 MySQL 8h 空闲断连），`autoflush=False`。

MySQL 适配约定：无真 BOOLEAN，用 `Boolean`（映射 TINYINT(1)）；JSON 字段一律用 `Text` 存 JSON 字符串，以对齐 PRD 建表 SQL。

### 无迁移框架

没有 Alembic。`create_all()` **只建缺失的表，不给已有表增加列或索引**；`python -m app.seed.apply_comments` 只补已有字段的注释，不能替代迁移。存量库升级参见 `app/seed/migrate_v21.py`、`migrate_article_soft_delete.py` 和 `migrate_homework_review.py`。作业批改迁移前先备份、停止业务写入并确认连接，先运行 `python -m app.seed.migrate_homework_review --check`，再按脚本说明执行；留意 MySQL DDL 隐式提交和已有空档位表的处理。

### 积分规则的两个语义陷阱

`point_rules.daily_limit` 是「**每天最多 N 次**」，不是积分上限。`checkin_daily = {points: 5, daily_limit: 1}` 意为「每天签到 1 次，每次给 5 分」。命中次数上限时 `award()` 直接返回 0，**不做部分发放**。唯一例外是游戏（`award_game()`），那里 `daily_limit` 当作**跨规则的当日积分总和上限**，超出时按剩余额度部分发放。

`point_logs` 表没有 `rule_key` 列，按 `type` 区分流水。家长扣分 `consume()` 走负数流水 + `operator_id`，**不查 `point_rules`**。作业批改使用独立的 `homework_review_rules` 档位和 `review` 流水；重批改按目标变化调整积分，余额不足时扣至零、未扣足部分永久豁免，实际累计变动可能不同于目标积分。

### 其它值得知道的实现

- **积分规则缓存**：`app/services/point_rule_service.py` 进程内单例 + `threading.Lock` + 60s TTL，admin 改规则后调 `invalidate(rule_key)` 精确失效。
- **数独是算法生成**，不预置题库：回溯生成完整解 → 按难度挖空（easy 36 / medium 48 / hard 54 空）→ 校验唯一解。学生提交由服务端复核。
- **阅读心跳防挂机**：客户端声明 `seconds`，服务端校验 `seconds <= 30 + 10`，超限则本次不计分但仍记录。
- **成语游戏会话在内存**（`app/routers/games.py` 的 `SessionStore` + `threading.Lock`），60 秒限时，**不落库**，多进程部署会丢会话。
- **bcrypt 直用原生库，不用 passlib**（passlib 1.7.4 读 bcrypt 4.1+ 已移除的 `__about__.__version__`，每次加载 backend 都打印告警）。两种实现哈希格式一致，存量可校验。`passlib[bcrypt]` 只作为测试依赖。

## Web 端架构

```
src/
├── api/         client.ts（axios 实例 + post 封装）+ auth/classes/student/parent/adminIdioms + types.ts
├── components/  AdminLayout.tsx、ReviewModal.tsx 等公共组件
├── router/      index.tsx（路由 + 角色守卫）
├── store/       auth.ts（Zustand 单一 store）
└── pages/       common/ student/ teacher/ admin/ parent/
```

- **代理**：`vite.config.ts` 把 `/api` 代理到 `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）并 rewrite 掉 `/api` 前缀——服务端路由**没有** `/api` 前缀（是 `/auth`、`/classes`…），不 rewrite 会 404。`loadEnv` 第三参为空串，故 `VITE_PROXY_TARGET` 可被运行时环境变量覆盖（`dev.sh` 就是这么注入的）。
- **API 层**：`api/client.ts` 里 `post<T>()` 封装统一响应，`code !== 0` 时抛带 `code` 属性的 Error。**没有 401/403 全局拦截**——运行期 token 过期不会自动登出，只在应用启动的 `store/auth.ts` `init()` 里做一次 `/auth/me` 探测并清 localStorage。
- **角色分流两段式**：路由守卫 `Protected roles={[...]}`（`router/index.tsx`）+ 菜单白名单 `MENUS: Record<Role, NavItem[]>`（`components/AdminLayout.tsx`）。admin 首登未改密会被强制跳到 `/change-password`。
- **状态**：Zustand 单一 store，手动读写 localStorage（key `token` / `user`），无 persist 中间件。
- **路由无懒加载**：`router/index.tsx` 静态 import 全部页面，无 `lazy`/`Suspense`。
- **页面数据获取**：`useCallback` + `useEffect` + `useState` 三件套，`Promise.all` 并发拉取，错误走 `message.error`。全站无 react-query。
- **已知职责错位**：`api/parent.ts` 里混放了 admin 的全部接口（invite/user/rule/article/stats），文件命名与内容不符。

**部署**：`Dockerfile` 两阶段（node:20-alpine 构建 → nginx:alpine），`nginx.conf` 配了 `location /api/` 反代到 `http://server:8000/`、`client_max_body_size 12m`（作业文件上传）、SPA 回退 `try_files ... /index.html`。但仓库里**没有 docker-compose.yml**，且 `.env.production` 的 baseURL 是绝对地址 `https://api.example.com`（占位符），与 nginx 的 `/api/` 反代语义互斥——生产构建前必须确认走哪条路。

## 移动端架构

```
lib/
├── main.dart            RootGate 角色路由守卫 + MaterialApp（内联 Material3 主题）
├── core/                config.dart（--dart-define）/ models.dart / api_client.dart / apis.dart
├── state/auth_state.dart  AuthState extends ChangeNotifier（Provider）
├── pages/               common/ student/ parent/ teacher/ admin/
└── widgets/common.dart  LoadingView/EmptyView/ErrorView/StatCard/showSnack
```

- **路由：无 go_router，无 named routes 表**。`MaterialApp` 只有 `home: RootGate`，没有 `routes:`/`onGenerateRoute`，因此**不能用 `Navigator.pushNamed`**（会抛 `Could not find a generator for route`）。页面跳转一律用 `Navigator.push(MaterialPageRoute(...))`。
- **登录/改密后的跳转由 `RootGate` 自动完成**：`AuthState.login()` / `markPasswordChanged()` 会 `notifyListeners()`，`RootGate`（`main.dart`）`context.watch<AuthState>()` 后按 `user.role` switch 到对应角色首页。页面里**不要**再写 `pushReplacementNamed('/home')` 这类跳转。
- **角色分流**在 `main.dart` 的 `RootGate`：未登录 → LoginPage；`mustChangePassword` → ChangePasswordPage；否则按 `user.role` switch 到 `StudentHome`/`ParentHome`/`TeacherHome`/`AdminHome`（每个都是 `IndexedStack` + `NavigationBar` 自绘 tab）。用 `ValueKey('${id}:${role}')` 在账号变化时重建，避免沿用上一个角色的导航状态。
- **API 层自研**：`core/api_client.dart` 单例 + `http` 包（不是 dio），全 POST，`code !== 0` 抛 `ApiException`，网络/超时统一转 `ServiceUnavailableError`。`core/apis.dart` 分 `AuthApi/StudentApi/TeacherApi/ParentApi/AdminApi` 五个单例约 70 个端点。
- **本地存储**：SharedPreferences 存 `token` 和 `user`（JSON 字符串）。Token 无刷新机制、无过期判断，靠启动时 `/auth/me` 兜底。Web 和移动端启动恢复时，只要 `/auth/me` 失败（包括网络故障）就会清除本地登录信息；运行期间 `ApiClient` **无 401 自动登出**。

### 渠道（flavor）机制

**渠道不由 `pubspec.yaml` 声明**（`flavors:` 不是 pubspec 的合法键，Flutter 从不读它；该键已从两端 pubspec 删除，只留注释说明）。真正的渠道由 `scripts/build.sh` 在打包时**动态改写平台工程**：

- Android：`scripts/lib/android_flavor.py` 往 `build.gradle.kts` 注入 `flavorDimensions` + `productFlavors{dev/prod}`，并注入 `buildFeatures { resValues = true }`（AGP 9.x 默认关闭，否则报错），同时把 `AndroidManifest.xml` 的 `android:label` 改成 `@string/app_name`。
- iOS：`scripts/lib/ios_flavor.py` 往 `project.pbxproj` 塞 `Debug-Dev`/`Release-Dev`/`Profile-Dev` 三个 XCBuildConfiguration + 生成 `Dev.xcconfig` + 生成 `xcshareddata/xcschemes/Dev.xcscheme`。**scheme 名必须是 `Dev.xcscheme`**（Xcode 用文件名做 scheme 名），且配置模板必须取自 Runner target 而非 RunnerTests。

两个脚本都是幂等的（靠 `ZGTSPFLV` + sha1 派生的固定 object ID），原文件备份为 `*.bak`。

### 版本号

**只在 `pubspec.yaml` 的 `version: 1.0.0+1` 定义**。iOS 的 `Info.plist` 用 `$(FLUTTER_BUILD_NAME)` / `$(FLUTTER_BUILD_NUMBER)`，Xcode 界面上的版本号改了不起作用（Runner target 没有 `MARKETING_VERSION`）。

## 已知缺陷（已验证，动手前先看这里）

以下都是**已实测确认**的现存问题，不是猜测：

1. **服务端限流未实现**。`app/config.py` 定义了 `register_rate_limit` / `action_rate_limit`，`.env.example` 也配了，但整个 `app/` 里除定义处无第二处引用。

2. **移动端两端 `lib/` 需手工同步**，无 CI 校验（见「仓库形态」第 1 条）。已同步 `login_page.dart`、`student_home.dart`、`main.dart`；`config.dart` 的注释仍各写各的。

3. **`npm run lint` 必然失败** —— 仓库里没有 ESLint 配置文件（无 `.eslintrc*` / `eslint.config.*`），脚本是空壳。

4. **Web 无 401 全局拦截** —— 运行期 token 过期不会自动登出，只在应用启动的 `init()` 里做一次 `/auth/me` 探测。

5. **Web 路由无懒加载** —— 页面全静态 import，首屏包含全部页面。

6. **`api/parent.ts` 里混放了 admin 的全部接口**（invite/user/rule/article/stats），文件职责与命名不符。

7. **`.env.production` 与 `nginx.conf` 的 `/api/` 反代语义冲突** —— 生产 baseURL 是绝对域名 `https://api.example.com`（占位符），nginx 反代段形同虚设；且 nginx 反代指向的 `server:8000` 无 compose 支撑。

8. **移动端作业附件支持不完整**：独立仓库的 `submitHomework` 接受 `filePath` 但未将其附加到请求，学生端作业提交只传文本。`file_picker` 已用于文章文件选择，不可视为未使用依赖。

9. **`zg-tsp-docs/sys_doc/PRD.md` 2.2.1 与实现仍有出入**：PRD 第 4.1 节的建表 SQL 是 SQLite 方言，权威定义在 `zg-tsp-server/app/models/entities.py`。

## 历史修复记录

以下是此前的修复记录；移动端路径指独立仓库，当前聚合检出不包含移动端。实际状态应以正在修改的检出为准：

- **移动端 release APK 的 INTERNET 权限**：已在 `zg-tsp-android/android/app/src/main/AndroidManifest.xml` 主清单声明（Flutter 模板只在 `src/debug/`、`src/profile/` 声明，导致 release 包无网络权限）。`aapt2 dump permissions` 实测产物已含 `android.permission.INTERNET`。
- **移动端登录后崩溃**：原先 `pushReplacementNamed('/home')` / `pushNamed('/register')` / `pushNamed('/homework/${id}')` 在无路由表的 `MaterialApp` 上必抛 `Could not find a generator for route`。现已改为：登录/改密成功后交由 `RootGate` 监听 `AuthState` 自动按角色分流（不再做 Navigator 跳转），注册页与作业详情页改用 `MaterialPageRoute`。
- **Android release 签名**：`build.gradle.kts` 现从 `android/key.properties` 读取正式签名（模板见 `android/key.properties.example`），文件缺失时**自动回退 debug 签名**（仅内部测试，不可上架）。两条路径均已用临时 keystore 实测通过。
- **iOS 签名团队**：`build.sh` 支持 `DEVELOPMENT_TEAM` 环境变量，注入渠道 xcconfig（`ios/Flutter/Dev.xcconfig`），三个 `*-Dev` 构建配置同时继承；渠道已配置时也会重新校验更新。
- **iOS ATS**：`Info.plist` 已对 `localhost` / `127.0.0.1` 开明文 HTTP 豁免（未全局关闭 ATS），并补了 `NSPhotoLibraryUsageDescription` / `NSCameraUsageDescription`。
- **服务端 Dockerfile HEALTHCHECK**：改为显式 POST 探针（原先用 GET 探 POST-only 的 `/health`，永远 405）。
- **`.env.example` 的无效 `HOST` / `PORT`**：已删除，改为注明 host/port 由 uvicorn 命令行决定。
- **PRD 与实现不一致**：PRD 2.1 的 SQLite 已改为 MySQL 8；第 7 节接口清单已补 `POST /games/idiom/question`。
- **移动端 pubspec**：无效的 `flavors:` 键已删除（Flutter 不读它），改为注释说明真实机制；`sdk` 约束从 `>=3.4.0` 对齐到 `>=3.13.0`；`file_picker` 升到 `^10.3.10`（8.x 的插件 compileSdk 仍是 android-34，会导致 AAR metadata 校验失败、release 构建中断）。
- **`independence_check.py` 第 6 项**：原先 grep pubspec 的 `flavors:` 键判断双渠道，与真实机制不符，已改为校验 Android `productFlavors{dev,prod}` 与 iOS `ios_flavor.py` 生成器。

## 本机构建环境

`../zg-tsp-repos/` 是本机五个独立仓库的检出；Android 工程使用以下**国内网络适配**，其他环境应先核实配置：

- `gradle/wrapper/gradle-wrapper.properties`：`distributionUrl` 指向腾讯云镜像（官方地址 307 跳 GitHub 会超时；Gradle 本地缓存按 URL 哈希匹配，换 URL 就要重新下载）
- `build.gradle.kts` / `settings.gradle.kts`：阿里云 Maven 镜像优先，缺失构件自动回落官方源

**改动时务必确认构建的是哪份代码**：`scripts/build.sh` 与 `scripts/dev.sh` 优先使用有效的 `REPOS_DIR`，否则自动探测 `../zg-tsp-repos` → `$ROOT` → `~/zg-tsp-repos`。无效或不完整的覆盖值可能回退自动探测；检查脚本输出。当前聚合检出没有移动端，不能直接构建本快照的移动端。

`scripts/dev.sh` 现在会在启动前打印「代码来源与新鲜度报告」（REPOS_DIR 命中哪份代码、五模块 git 状态、与本快照的差异条目数），用它确认跑的是哪一份。

## 独立仓库重建后的 Android 构建（gradlew 已入库）

`scripts/split_repos.sh split` 用 `git subtree split` 重建 `../zg-tsp-repos/`，**被 `.gitignore` 排除的文件不会随重建带过去**。Android 侧的 gradle 包装器三件套已改为**入库**（`android/.gitignore` 移除了 `gradle-wrapper.jar` / `gradlew` / `gradlew.bat` 三行），所以独立仓库 clone 后 Android 构建开箱可用 —— 与 `gradle-wrapper.properties` 本就入库、且 `distributionUrl` 钉腾讯云镜像的做法一致。实测 `flutter create --platforms=android .` 不会改动已存在的这三个文件，不会来回冲突。

仍需 `flutter pub get` 生成的（被 gitignore，属正常）：`.flutter-plugins-dependencies`、`android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java`。

两个 `flutter create` 的副作用要留意：

- 它生成的 `test/widget_test.dart` 引用不存在的 `MyApp`（本工程根组件是 `ZgTspApp`），**留着会让 `flutter test` 编译失败**。两端 `.gitignore` 都已加 `test/widget_test.dart`，但文件已存在于工作区时需手动删除。
- 它触发的 `pub get` 会升级传递依赖（如 `image_picker_ios` 0.8.13+13→+14），与工程改动无关，用 `git checkout -- pubspec.lock` 还原。

## Git 约定

- 主分支 `main`。五个独立仓库通过 `git subtree split --prefix=<模块>` 拆出，历史保留在 `split/<模块>` 分支（当前本地无这些分支，需 `split_repos.sh split` 重新生成）。
- **服务端测试不入库**：`zg-tsp-server/tests/` 被 gitignore，本地测试属于联调资产，干净检出不一定存在。测试连接真实数据库且可能执行删除，使用专用隔离库。
- `.dev-logs/`、`/dist/`、`.venv/`、各 `.env`、`*.bak`（脚本注入渠道配置的备份）、`android/key.properties`、`ios/Flutter/{Dev,Prod}.xcconfig` 均不入库。
- 根 `.claude/settings.local.json` 只有 `permissions.allow` 一个节点（314 条），无 deny/ask/env/hooks/mcpServers 配置。
