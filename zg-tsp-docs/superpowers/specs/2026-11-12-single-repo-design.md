# 设计：单一仓库化（取消独立仓库区分）

- 日期：2026-11-12
- 状态：待评审
- 关联：`zg-tsp-docs/sys_doc/PRD.md`（v2.2 → v2.3）、`CLAUDE.md`、`README.md`

---

## 1. 背景与目标

`zg-tsp` 目前是**一个 git 仓库、三个模块目录**的形态，但仓库内保留着完整的「拆分为多个独立仓库」机制：
`scripts/split_repos.sh`、`split/*` 分支、`../zg-tsp-repos/` 三份独立检出，以及 README / CLAUDE.md / PRD 中
「本仓库已拆分为 3 个独立仓库、这里只是快照」的一整套叙述。

这套机制的实际负担：

- `scripts/dev.sh` 的「代码来源与新鲜度报告」要探测 `../zg-tsp-repos`、`~/zg-tsp-repos` 并逐目录做 diff 统计 ——
  在单仓库形态下这些差异恒为 0，纯粹是噪音和心智负担。
- `scripts/init.sh` 的探测顺序与 `dev.sh` **不一致**（前者先探 `../zg-tsp-repos`），成为「跑的是哪份代码」类问题的根源。
- 文档反复强调「本目录是快照，日常开发请在各自独立仓库进行」，但三个独立仓库**都没有 remote**，
  纯本地对象 —— 这个区分没有带来实际的发布收益。

**目标**：把 `zg-tsp` 收敛为**唯一开发源、唯一 git 仓库**，取消「独立仓库」的区分与相关机制，
同时把跨模块的约束从「仓库隔离」降级为「模块边界」继续保留。

### 1.1 明确不在本次范围内

- **微信小程序端**（`~/WeChatProjects/HomeworkPoints`）保持仓外独立仓库，本次不动其代码、不迁入本仓库。
  理由：原生小程序工具链（微信开发者工具）与 Python/Node 完全不同，且它是独立发布单元。
- **不重写 git 历史**。`main` 已包含三个模块的全部提交，`split/*` 分支本就是它的子树过滤，删除分支不丢历史。
- **不改目录名**。`zg-tsp-server/`、`zg-tsp-web/`、`zg-tsp-docs/` 三个目录名保持不变。

---

## 2. 终态

```
zg-tsp/                      ← 唯一 git 仓库，唯一开发源
├── zg-tsp-server/           Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8
├── zg-tsp-web/              React 18 / Vite 6 / Ant Design 5 / Zustand 5
├── zg-tsp-docs/             PRD + 契约 + 验收脚本
│   └── superpowers/specs/   设计文档
├── scripts/
│   ├── dev.sh               启动 / 停止 / 状态（简化后）
│   └── init.sh              数据库初始化（简化后）
├── Makefile                 ← 新增，根级统一入口
├── README.md
└── CLAUDE.md
```

### 2.1 关键区分：合并仓库 ≠ 取消模块边界

合并发生在**仓库层面**：不再有多个 git 仓库，不再有「拆分 / 推送独立仓」流程。

**模块边界继续保留**，具体表现为：

- 三个模块各自有独立的依赖清单（`requirements.txt` / `package.json`），不引入跨模块依赖。
- 三方源码之间零 import / 零路径引用（`independence_check.py` 检查项 2 继续生效）。
- 三个模块各自可单独安装依赖、单独启动、单独打包成部署产物。
- 服务端地址、数据库地址全部走外部配置，源码零硬编码。

这样做的收益：边界一旦被打破很难重建，保留边界的成本几乎为零；同时将来若真要再次拆分仓库，随时能拆。

---

## 3. 变更清单

### 3.1 删除拆分机制

| 对象 | 动作 | 备注 |
|---|---|---|
| `scripts/split_repos.sh` | 删除 | 拆分流程整体废弃 |
| `split/zg-tsp-server` | 删除分支 | 子树过滤，无独有提交 |
| `split/zg-tsp-web` | 删除分支 | 同上 |
| `split/zg-tsp-docs` | 删除分支 | 同上 |
| `split/zg-tsp-android` | 删除分支 | 移动端下线前历史留存；源码仍在 `main` 历史提交 `7bf7dd0` 之前，可恢复 |
| `split/zg-tsp-ios` | 删除分支 | 同上 |
| `../zg-tsp-repos/`（三份独立检出） | 删除目录 | 内容 `main` 已全部包含；无 remote，纯本地对象 |

**不可逆性说明**：以上均为本地对象删除，无 remote 兜底。执行前应确认 `main` 工作区干净、当前提交为
恢复基线。移动端源码的恢复路径是 `main` 的历史提交（`7bf7dd0` 之前），不依赖 `split/*` 分支。

### 3.2 脚本简化

#### `scripts/dev.sh`

删除：

- `find_repos_dir()` 的多候选探测（`$ROOT/../zg-tsp-repos`、`$HOME/zg-tsp-repos`）与 `REPOS_SOURCE` 追踪。
- `count_diff_files()` 与「与本快照的差异」整段统计。
- `report_module_git()` 中的「非独立仓库（聚合仓库形态）」标注 —— 单仓库下必然命中，等于噪音。
- `report_source()` 整体（「代码来源与新鲜度」报告）。

保留：

- `REPOS_DIR` **环境变量显式覆盖**仍然生效（供 git worktree 等场景指向别处检出），默认即 `$ROOT`。
  显式指定但路径无效时，明确告警并回落到 `$ROOT`（不静默回退）。
- `SERVER_PORT` / `WEB_PORT` / `API_TARGET` / `VENV_PY` 等既有环境变量语义不变。
- POSIX `sh` 兼容约束不变（不用数组、`[[ ]]`、进程替换）。

预计脚本从约 400 行降到约 200 行。

#### `scripts/init.sh`

- 探测顺序简化为：环境变量 `REPOS_DIR` → `$ROOT`。删除 `../zg-tsp-repos`、`~/zg-tsp-repos` 两个候选。
- 其余逻辑（`DATABASE_URL` 解析、admin 密码哈希生成与占位符替换、表/外键/规则数量校验）**完全不变**。

#### `zg-tsp-docs/scripts/independence_check.py`

- 定位从「模块独立性（独立仓库之间无耦合）」改为「**模块边界检查**（单仓内三模块互不越界）」。
- **检查项实质全部保留**，仅第 1 项措辞由「各模块有独立依赖清单」保持不变，其余判定逻辑不动。
- 仓库根定位改为向上两级（`zg-tsp-docs/scripts/` → `zg-tsp-docs/` → 根），不依赖 `../zg-tsp-repos`。
- 文档字符串中的「需在聚合仓库下运行」改为「需在仓库根下运行」。

#### `zg-tsp-docs/scripts/acceptance_check.py`

- 路径引用与判定逻辑不变（本来就是在 `zg-tsp-docs/scripts/` 内定位仓库根）。

### 3.3 根级 Makefile（新增）

新增 `/Makefile`，用系统自带 `make`，不引入任何新依赖。目标：

| 目标 | 行为 |
|---|---|
| `make help` | 默认目标，列出可用目标 |
| `make dev` | 转发 `scripts/dev.sh`（起服务端 + Web 端） |
| `make server` / `make web` | 转发 `scripts/dev.sh server` / `web` |
| `make stop` / `make status` / `make logs` | 转发 `scripts/dev.sh` 对应子命令 |
| `make db-init` | 转发 `scripts/init.sh` |
| `make test` | 服务端 `pytest`（在 `zg-tsp-server/` 下执行） |
| `make build` | Web `npm run build`（`tsc -b && vite build`，含类型检查） |
| `make check` | 依次跑 `independence_check.py` 与 `acceptance_check.py` |

约束：

- `make check` 中的 `acceptance_check.py` 需要**服务端已启动**且需要管理员密码
  （`ACCEPTANCE_ADMIN_PASSWORD` 环境变量），Makefile 只做透传，不内置任何凭据。
- `make test` 与 `make check` 会写入真实数据库，Makefile 的帮助文本中标注这一点。
- `make test` 需要**可连的 MySQL**；`zg-tsp-server/tests/` 被 gitignore，干净检出下该目标会因无测试文件而
  空跑 —— 帮助文本中说明，不视为失败。
- Makefile 调用 Python 时优先用仓库根的 `.venv/bin/python`，不存在则回落 `python3`
  （与 `scripts/dev.sh` 的 `server_python()` 策略一致）。
- `make` 的 `.PHONY` 声明覆盖全部目标，避免与同名文件冲突。

### 3.4 文档重写

| 文件 | 改动 |
|---|---|
| `README.md` | 删除「本仓库已拆分为 3 个独立仓库」「聚合检出」「拆分方式」三节；改为单仓库三模块说明 + Makefile 入口 + 现有快速开始 |
| `zg-tsp-docs/README.md` | 同上口径；仓库表格去掉「独立仓库」列，保留模块职责与技术栈 |
| `CLAUDE.md` | 改「仓库形态」章节；三个结构性事实第 2 条改为「`scripts/dev.sh` 默认启动本目录代码，`REPOS_DIR` 可显式覆盖」；删「本机构建环境」中 `../zg-tsp-repos` 相关段落；「Git 约定」删子树拆分段落，改为「单仓三模块目录，模块边界保留」 |
| `zg-tsp-docs/sys_doc/PRD.md` | **决策 6 改写**（详见 3.5）；版本号 v2.2 → v2.3；§0 变更记录新增 v2.3 条目；§2.2 项目结构、§2.2.1 模块独立性原则、§2.2.2 各模块独立启动与打包、§9.6、§11 开发计划、§12 验收标准、§13 决策表、§13.1 决策衍生需求逐处同步 |
| `zg-tsp-docs/sys_doc/小程序.md` | 「不改动现有三仓结构与 `split_repos.sh`」的理由改为「小程序是独立发布单元、构建与审核节奏不同、工具链不兼容」；「与本仓库的关系」章节措辞更新 |
| `zg-tsp-docs/sys_doc/config.md` / `迭代.md` | 若含仓库形态表述则同步（实施时逐一核对） |

### 3.5 PRD 决策 6 的改写

PRD 现行表述（§2.2 末尾）：

> **决策 6**：三个模块拆分为**独立仓库**发布，本目录为聚合与文档同步用；
> 接口契约以第 7 节为唯一权威来源。小程序端为第四个独立仓库，不在本聚合检出内。

改写为：

> **决策 6（2026-11-12 修订）**：三个模块置于**同一仓库**的独立目录中（`zg-tsp-server/`、`zg-tsp-web/`、
> `zg-tsp-docs/`），各模块保留独立依赖清单与独立打包能力，模块间零代码引用。
> 接口契约以第 7 节为唯一权威来源。微信小程序端为**仓外独立仓库**，不在本检出内。

#### 3.5.1 §2.2 项目结构

- 第 94 行「按端/形态拆分为三个**相互独立**的模块」保留，但「单独发版」改为「单独构建与发布」。
- 第 101-102 行小程序端说明保留事实，措辞「独立仓库，位于本聚合检出之外」→「仓外独立仓库，不在本检出内」。
- 第 105 行目录树注释 `# 三个独立仓库同级检出（联调用）` → `# 单一仓库，三个模块目录`。
- 第 146-151 行的两段引用（仓库形态 + 决策 6）合并为一段新表述（见上）。

#### 3.5.2 §2.2.1 模块独立性原则

标题「模块独立性原则」→「**模块边界原则**」。**表格六行全部保留**，仅措辞随语义调整：

- 「无源码依赖」不变。
- 「依赖自封闭」不变。
- 「配置外置」不变。
- 「单独启动」不变。
- 「单独打包」不变（模块仍独立构建产物、独立版本号）。
- 「版本契约」不变。

#### 3.5.3 §2.2.2 各模块独立启动与打包

命令块与打包方式**完全不变**。第 192 行小程序端「不参与本目录的拆分与联调」→「不参与本目录的联调」。

#### 3.5.4 §9.6 平台实现分工

第 1056 行「小程序端为**独立仓库**（决策 6），位于本聚合检出之外」→「仓外独立仓库，不在本检出内」。

#### 3.5.5 §11 开发计划

第 1108 行 P8 行「（独立仓库，一期学生 + 家长）」→「（仓外独立仓库，一期学生 + 家长）」。

#### 3.5.6 §12 验收标准 —「模块独立性」清单组

这一组条目部分基于「各自独立检出」措辞，需逐条改写为模块边界语义：

| 现行条目 | 改写后 |
|---|---|
| 各模块均可**单独检出**、单独安装依赖、单独启动，互不依赖其他模块的构建产物 | 各模块均可单独安装依赖、单独启动，互不依赖其他模块的构建产物（**删去「单独检出」**） |
| 任一模块重新构建/发版，不触发也不破坏其他模块 | 保留（模块独立构建与发布仍成立） |
| 任一模块的源码中不含对其他模块的 import / 路径引用 / 构建期依赖 | 保留 |
| 服务端不可用时，Web 能正常启动并给出降级提示，不崩溃 | 保留 |
| 服务端地址均为外部配置项，代码中无硬编码地址 | 保留 |
| 各模块可独立版本化发布；服务端小版本升级不强制客户端同步发版 | 各模块可独立构建与发布（独立产物、独立版本号）；服务端小版本升级不强制客户端同步发版（**版本号本身是仓库级的**） |
| 其余小程序端条目 | 保留 |

#### 3.5.7 §13 决策表 与 §13.1 决策衍生需求

- 决策表第 6 行「仓库形态：**独立仓库**，非 monorepo（小程序端为第四个仓库，在聚合检出外）」
  → 「仓库形态：**单仓三模块目录**，模块边界保留（小程序端为仓外独立仓库）」。
- 决策表第 1 行「独立仓库，满足模块独立性」→「仓外独立仓库，满足模块边界」。
- §13.1「决策 6 衍生」：现文「各模块拆分独立仓库后，接口契约需有唯一权威来源；本文档（第 7 节接口清单）即为契约基线，各仓库以其为准」
  → 「三个模块合并到单仓后，接口契约仍需唯一权威来源；本文档（第 7 节接口清单）即为契约基线，各模块以其为准」。
- §13.1 其余条目不动。

#### 3.5.8 §0 变更记录

新增 v2.3 条目，摘要本次仓库形态修订。

### 3.6 完全不受影响的部分

目录名不变，因此以下内容零改动：

- 所有 `zg-tsp-server/...`、`zg-tsp-web/...`、`zg-tsp-docs/...` 路径引用。
- `zg-tsp-server/scripts/server_package.sh`、`zg-tsp-web/scripts/web_package.sh`（产物名与目标机路径不变）。
- `zg-tsp-server/deploy/`、`zg-tsp-web/deploy/`（目标机路径为 `/opt/zg-tsp/server`、`/var/www/zg-tsp-web`）。
- Web 端 `VITE_API_BASE_URL`、`vite.config.ts` 的代理前缀、API 契约路径。
- 小程序端全部代码。
- 根 `.gitignore`（`/zg-tsp-server/tests/`、`/docs/` 等路径规则仍然正确）。

---

## 4. 执行顺序与验证

### 4.1 执行顺序

1. 提交当前工作区已有的未跟踪改动（如 `zg-tsp-web/src/pages/parent/Homework.tsx`、`zg-tsp-server/deploy/`、
   `zg-tsp-server/scripts/` 等 —— 这些目前**未纳入 git 跟踪**），确保基线干净。
2. 删 `scripts/split_repos.sh`；简化 `scripts/dev.sh`、`scripts/init.sh`；改写 `independence_check.py`。
3. 新增 `Makefile`。
4. 改写 `README.md`、`zg-tsp-docs/README.md`、`CLAUDE.md`、`PRD.md`、`小程序.md`。
5. 打归档 tag `archive/pre-merge-2026-11-12`（指向当前 `main`），再删四个 `split/*` 分支与 `../zg-tsp-repos/`。
   删除前逐个确认 `../zg-tsp-repos/*` 无未提交改动（`git -C <dir> status --porcelain` 为空）。
6. 验证（下节）。

### 4.2 验证

| 项 | 命令 | 通过标准 |
|---|---|---|
| 模块边界检查 | `make check` 里的 `independence_check.py` 部分 | 8/8 通过 |
| 服务端可启动 | `make server` | 端口 8000 起来，`curl -X POST .../health` 返回 `code:0` |
| Web 可构建 | `make build` | `tsc -b && vite build` 无错误 |
| 两端可联调 | `make dev` | Web 5173 起来，代理到 8000 不 404 |
| 业务验收 | `make check` 里的 `acceptance_check.py` 部分 | 与合并前一致（需服务端已启动 + `ACCEPTANCE_ADMIN_PASSWORD`） |
| 仓库无残留 | `grep -rn "split_repos\|zg-tsp-repos" . --exclude-dir={.git,node_modules,superpowers}` | 除本设计文档（`zg-tsp-docs/superpowers/` 已排除）与「已废弃」说明性提及外，无引用 |

**回归重点**：`dev.sh` 简化后最容易出 bug 的是 POSIX sh 语法与 PID 文件处理。简化时保留原有的
「启动前不清 PID 文件、`start_bg` 用 `exec` 拿真实 pid、`stop` 兜底按端口清理」这三条语义，
并在 macOS 的 `sh`（bash 3.2 兼容模式）与 `zsh` 下各跑一次 `make dev` / `make stop`。

---

## 5. 风险与影响

| 风险 | 影响 | 缓解 |
|---|---|---|
| 删除 `../zg-tsp-repos/` 与 `split/*` 不可逆 | 若有人仍在独立仓工作，其本地改动会随目录删除而丢失 | 删除前逐个 `git -C ../zg-tsp-repos/* status` 确认无未提交改动；确认后先打一个归档 tag `archive/pre-merge-2026-11-12` 再删分支 |
| PRD 决策 6 改写后与小程序端表述冲突 | 文档自相矛盾 | 同批改完 PRD §2.2.1 / §9.6 / §13 / §16 与 `小程序.md`，逐处核对「第四个独立仓库」字样 |
| `dev.sh` 简化引入 shell 回归 | 启停失败 | 保留原 PID/端口语义；macOS `sh` + `zsh` 双跑验证 |
| `make check` 写入真实数据库 | 污染共享数据 | Makefile 帮助文本标注；沿用现有验收脚本的跳过策略 |

---

## 6. 不做的事（明确排除）

- 不迁移微信小程序端进本仓库。
- 不改三个模块目录名。
- 不重写 git 历史、不 squash 现有提交。
- 不引入根级 `package.json` workspace 或根 `pyproject.toml`（Makefile 已够；避免引入新的依赖管理）。
- 不改服务端 / Web 的任何业务代码、接口契约、数据库结构。
- 不改部署产物名称与目标机安装路径。
