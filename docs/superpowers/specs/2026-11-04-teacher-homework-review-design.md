# 老师端作业审批（批改）功能设计

- 日期：2026-11-04
- 状态：待实施
- 涉及仓库：`zg-tsp-server`、`zg-tsp-web`、`zg-tsp-android`、`zg-tsp-ios`、`zg-tsp-docs`

---

## 1. 背景与目标

### 1.1 现状

PRD 5.3 规定「用时 <1 分钟标记待审核（异常）」，实现中确有 `suspicious` 标记（运行时由 `duration_minutes < 1` 计算，非落库字段），老师端 `HomeworkRecords.tsx` 会显示「⚠ 待审核」，学生端 `HomeworkDetail.tsx` 显示「已标记待老师审核」。

但系统**没有任何审核动作**——`suspicious` 只是一个只读标签，闭环在此断裂。`homework_records` 表也没有任何承载老师批改结果的字段。

### 1.2 目标

为老师端增加**批改打分 + 写评语**能力：

1. 老师可对已提交的作业打分数（0–100）并写评语
2. 分数按可配置的档位规则换算为**额外积分**追加发放
3. 允许改分，积分按**差额补发/回扣**，账实一致
4. 学生端可见分数与评语
5. 老师可查看待批改清单
6. admin 可配置分数档位

### 1.3 非目标（本次不做）

- 不做「异常作业专项审批」（通过/驳回可疑提交）——批改功能已覆盖老师的审核动作
- 不做批改历史留痕（每次改分只保留最新结果，不存流水历史）
- 移动端不做 admin 档位配置页（对齐现有 admin 移动端精简定位）
- 移动端不做「待批改汇总页」，批改入口挂在已有作业完成情况页内
- 不做批改后的学生申诉/二次提交

---

## 2. 需求确认结论

brainstorming 阶段与用户确认的决策：

| 议题 | 结论 |
|------|------|
| 审批语义 | 批改打分 + 写评语 |
| 分数与积分关系 | 分数换算为**额外积分**（提交时已自动发的 10/5 分不动） |
| 换算规则来源 | 走可配置规则，admin 可改（**新建 `homework_review_rules` 档位表**） |
| 重复批改 | 允许改分，积分**差额补发** |
| 实现端 | 服务端 + Web + 移动端老师端（学生端可见结果） |
| 学生端可见性 | 显示分数 + 评语 |
| 改分时余额不足 | **扣到 0 为止，不追扣**，记流水记实际扣减额 |

---

## 3. 数据模型

### 3.1 `homework_records` 新增字段

方案 A：直接在既有表上加字段。一个学生一次作业只有一行记录，改分即 UPDATE 该行，无需处理多记录合并。

| 字段 | 类型 | 可空 | 默认 | 含义 |
|------|------|------|------|------|
| `review_score` | Integer | 是 | NULL | 批改分数 0–100，NULL 表示未批改 |
| `review_comment` | Text | 是 | NULL | 老师评语 |
| `reviewed_at` | DateTime | 是 | NULL | 批改时间 |
| `reviewed_by` | Integer (FK users.id) | 是 | NULL | 批改老师 ID |
| `review_points` | Integer | 否 | 0 | 本条记录**实际已发放**的批改积分，用于差额计算 |

新增索引：

```sql
CREATE INDEX ix_homework_records_pending ON homework_records (homework_id, reviewed_at);
```

用途：支撑「待批改」列表查询（`submit_time IS NOT NULL AND reviewed_at IS NULL`）。

### 3.2 新建 `homework_review_rules` 表

分数档位 → 积分的映射。与 `point_rules` 结构不同（后者是单值规则，前者是档位区间），故独立建表。

```sql
CREATE TABLE homework_review_rules
(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    min_score  INTEGER NOT NULL UNIQUE,  -- 档位下限（含）
    points     INTEGER NOT NULL,         -- 该档位发放的积分
    enabled    BOOLEAN  DEFAULT 1,       -- 停用则跳过该档
    updated_by INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**匹配规则**：取所有 `enabled` 且 `min_score <= score` 的档位中 `min_score` 最大的一档。无匹配则发 0 积分（不报错）。

**种子数据**：

| min_score | points | 说明 |
|-----------|--------|------|
| 90 | 5 | 优秀 |
| 80 | 3 | 良好 |
| 60 | 1 | 合格 |

低于 60 分无匹配档位，发 0 积分。

### 3.3 积分流水类型

`point_logs.type` 新增取值 `review`，与提交时自动发放的 `homework` 类型隔离。这样「本条记录已发了多少批改积分」可从 `review_points` 字段直接读出，差额计算不依赖对流水的反查。

### 3.4 迁移

本项目无 Alembic，`create_all()` 只建缺失表、不改已有表结构。存量库需要：

1. 改 `zg-tsp-server/app/models/entities.py`
2. `python -m app.seed.export_ddl` 重新生成 `zg-tsp-docs/sql/init.sql`
3. 新增幂等迁移脚本 `zg-tsp-server/app/seed/migrate_homework_review.py`：
   - 对 `homework_records` 执行 `ALTER TABLE ... ADD COLUMN`（先查 `information_schema` 判断列是否存在，存在则跳过）
   - 创建 `homework_review_rules` 表 + 索引（`create_all()` 也能建，此处仅为保证单脚本自洽）
   - 写入档位种子数据（`INSERT ... ON DUPLICATE KEY UPDATE` 或先查后插）
4. `python -m app.seed.apply_comments` 补齐 COMMENT

脚本需支持 `--check` 只读模式（与 `apply_comments` 风格一致）。

---

## 4. 服务端设计

### 4.1 新增接口

全部 POST，参数进 JSON Body，响应 `{code, message, data}`。

| 接口 | 角色 | 请求 | 响应 data |
|------|------|------|-----------|
| `/homework/review` | teacher | `{homework_id, student_id, score, comment?}` | `{record, points_delta, awarded_points}` |
| `/homework/pending` | teacher | `{page, size}` | `{list, total, page, size}` |
| `/homework/review-rules/list` | admin | `{}` | `{list}` |
| `/homework/review-rules/update` | admin | `{id, points?, enabled?}` | `{rule}` |
| `/homework/review-rules/create` | admin | `{min_score, points}` | `{rule}` |

`/homework/review-rules/list` 这三个接口的 router 归属：放在 `app/routers/homework.py` 内（路径前缀已是 `/homework`），admin 权限用 `require_admin` 依赖。**注意**：本项目 `/admin` 组是整组锁死 admin 的独立前缀，此处若放 `/homework/review-rules/*` 需在函数体首行判角色，与其他 router 的 `_require_*` 私有 helper 风格一致。

### 4.2 批改接口的积分差额算法

```
target  = 匹配档位(score).points      # 无匹配则 0
granted = record.review_points        # 实际已发放
delta   = target - granted

delta > 0  → 发放 delta（point_logs.type='review'，points=+delta）
delta < 0  → 回扣，见 4.3
delta == 0 → 不动积分，仅更新分数与评语
```

`record.review_points` 始终等于「实际已发放的批改积分」，与流水一致。

### 4.3 回扣与余额不足

`point_service.consume()` 要求余额充足，否则抛 `PointError`。老师改低分数时可能扣超过学生余额，直接用 `consume()` 会让改分操作失败、卡死老师流程。

**处理方式**：回扣时实际扣减额 = `min(待扣数, 学生当前余额)`。

- 扣到 0 为止，**不报错**
- 流水记**实际扣掉的数**（负值），`type` 同为 `'review'`
- `review_points` 同步减实际扣掉的数
- 欠额不追扣

回扣流水与发放流水**同为 `type='review'`**：这样「某条作业记录的批改积分净额」= 该记录所有 `type='review'` 流水之和，与 `review_points` 天然对齐，便于对账。

**举例**：首次批 90 分发 5 分（`review_points=5`），学生花掉积分后余额剩 2 分，改成 60 分（应发 1 分）→ 差额 -4，余额仅 2 → 实扣 2 分，`review_points` 变 3，流水记 -2。账面 3 分 > 目标 1 分，但已无法再扣。

> 该情形下账面与目标短暂不一致是**有意为之**：追扣需要跨期欠款账本，超出本次范围。

### 4.4 并发控制

批改接口对目标 `homework_records` 行加锁：`SELECT ... FOR UPDATE`（SQLAlchemy 的 `with_for_update()`）。

目的：防止两个老师同时批改同一份作业，导致双方都读到同一个 `granted` 值并各自发放，造成积分重复发放。

这是本项目**首次使用行锁**，实现需注意：

- 仅 MySQL 生效（本项目不用 sqlite，无兼容问题）
- **锁两行**：`homework_records` 行（防同一份作业重复发积分）+ `users` 行（防同一学生多份作业并发批改时余额互相覆盖）
- **锁序固定**：`homework_records` → `users`。每次批改只涉及一条作业记录与一个用户，锁序一致故无死锁
- 事务内先锁记录，再锁用户，再读 `users.total_points` 计算余额

### 4.5 权限与校验

| 校验 | 实现 | 错误 |
|------|------|------|
| 必须是 teacher | `_require_teacher(user)` | 403 仅老师可执行此操作 |
| 班级归属 | `_own_class_or_403(db, teacher, hw.class_id)` | 403 只能操作自己班级的数据 |
| 记录存在 | 记录不存在或未提交 → 400 学生尚未提交，不可批改 |
| 分数范围 | Pydantic `Field(ge=0, le=100)` | 400 分数需在 0–100 之间 |
| 档位配置权限 | 函数体首行判 `role == admin` | 403 仅管理员可配置批改档位 |
| 档位下限唯一 | 新增档位时查 `min_score` 是否已存在 | 400 该分数档位已存在 |

### 4.6 数据流

```
老师填分数/评语
  → POST /homework/review
    ① _require_teacher + _own_class_or_403
    ② SELECT ... FOR UPDATE 锁定 homework_records 行
    ③ 校验 submit_time 非空
    ④ target = 匹配档位(score)；granted = record.review_points；delta = target - granted
    ⑤ delta>0 → awarded = award_amount(delta, type='review')
       delta<0 → awarded = -deduct_amount(|delta|, type='review')，扣至余额为 0
       delta==0 → awarded = 0
       其中 awarded 是**实际净变动**（正=实发，负=实扣）
    ⑥ review_points = granted + awarded
       更新 review_score / review_comment / reviewed_at / reviewed_by
    ⑦ commit
  → 返回 {record, points_delta, awarded_points}
```

**两个返回字段的语义**：

| 字段 | 含义 |
|------|------|
| `points_delta` | 目标差额（`target - granted`）。正=应补发，负=应回扣。**规则层面**的差额，与学生余额无关 |
| `awarded_points` | 实际积分**净变动**。正=实发，负=实扣。余额不足时其绝对值小于 `|points_delta|` |

举例：首次批 90 分发 5 分（`review_points=5`），学生花到只剩 2 分，改成 60 分 → `points_delta = 1 - 5 = -4`（应扣 4），但余额只有 2 → `awarded_points = -2`（实扣 2），`review_points = 5 + (-2) = 3`。

### 4.7 响应字段扩展

`_record_to_dict()` 新增 `review_score` / `review_comment` / `reviewed_at` / `review_points`，老师端 `/homework/records` 与学生端 `/homework/detail` 的 `my_record` 均复用该函数，自动带上批改字段。

### 4.8 待批改列表

`/homework/pending` 跨作业汇总该老师所有班级的待批改记录：

- 关联 `homework_records` → `homework` → `users`（学生）
- 过滤 `submit_time IS NOT NULL AND reviewed_at IS NULL`
- 返回学生名（nickname 优先，回落 username）、学生 ID、作业标题、提交时间、用时、`suspicious` 标记
- 分页 `{list, total, page, size}`

### 4.9 积分服务扩展

现有 `point_service.award()` 的签名是 `award(db, student_id, type_, rule_key, ...)`——积分值取自 `point_rules` 表，**不能发放任意数额**。批改积分的值来自档位表、且不设日上限（一个学生一天可能被批改多份作业），因此需要在 `app/services/point_service.py` 新增直接写流水的方法：

```python
def award_amount(
    db: Session,
    student_id: int,
    amount: int,
    type_: str,
    remark: str | None = None,
    operator_id: int | None = None,
) -> int:
    """按指定数额发放积分（不经 point_rules，无日上限）。

    amount <= 0 时直接返回 0，不写流水。同步累加 users.total_points。
    """
```

配套的回扣方法：

```python
def deduct_amount(
    db: Session,
    student_id: int,
    amount: int,
    type_: str,
    remark: str | None = None,
    operator_id: int | None = None,
) -> int:
    """回扣积分（不经 point_rules）。

    实际扣减 = min(amount, 当前余额)，扣至 0 为止，不抛异常。
    返回实际扣减额；无余额可扣时返回 0。
    """
```

两者都写 `point_logs` 并同步 `users.total_points`，与既有 `award` / `consume` 的行为约定一致（`total_points` 不为负）。

---

## 5. Web 端设计

### 5.1 老师端

**改造现有页** `src/pages/teacher/HomeworkRecords.tsx`：

1. 表格新增两列：`分数`、`评语`
2. 每行新增「批改」按钮 → 打开 Modal：
   - 顶部展示学生作答原文（`text_content`，可换行展示）与附件链接（`file_url`，新窗口打开）
   - 分数输入（`InputNumber`，0–100，默认 100）
   - 评语输入（`Input.TextArea`）
   - 已批改的记录预填原分数与评语
   - 提交调 `/homework/review`，成功后刷新表格
3. 已批改行显示分数 `Tag`（≥90 绿 / ≥80 蓝 / ≥60 橙 / <60 红），按钮文案改为「修改批改」

**新增待批改页** `src/pages/teacher/HomeworkPending.tsx`：

- 表格列：学生、学生 ID、作业标题、提交时间、用时、异常标记、操作
- 「批改」按钮 → 同一套批改 Modal
- 异常标记沿用现有 `suspicious`（用时 <1 分钟）逻辑
- 空态：「没有待批改的作业」

**入口**：`src/pages/teacher/Homework.tsx` 作业列表页顶部加「待批改 N」按钮（`Badge` 计数），点击跳转 `/teacher/homework/pending`。计数来自 `/homework/pending` 接口的 `total`（取第 1 页的 total 即可）。

**路由**：`src/router/index.tsx` 新增 `/teacher/homework/pending`，放在既有 teacher 角色守卫内。

### 5.2 学生端

`src/pages/student/HomeworkDetail.tsx`：

- `rec.reviewed_at` 非空时，在 `Descriptions` 下方新增「老师批改」卡片：
  - 分数（大号数字 + 颜色 Tag）
  - 评语文本
  - 批改时间
- 未批改时显示 `Alert`「老师尚未批改」

### 5.3 admin 端

`src/pages/admin/Rules.tsx` 现有「积分规则管理」Card **下方新增** Card「作业批改档位」：

- 表格列：分数下限、积分值、启用开关、操作
- 「新增档位」按钮 → Modal 表单（`min_score` / `points`）
- 「编辑」按钮 → Modal 修改积分值与启停
- 档位下限唯一，重复时后端报错并提示

### 5.4 API 层与类型

- `src/api/classes.ts` 的 `homeworkApi` 新增 `review`（批改）与 `pending`（待批改列表）
- `src/api/parent.ts` 新增三个档位接口 `reviewRulesList` / `reviewRuleUpdate` / `reviewRuleCreate`——该文件虽名为 parent，但现状已混放全部 admin 接口（invite/user/rule/article/stats），档位配置属 admin 域，沿用现状，不做文件拆分（超出本次范围）
- `src/api/types.ts` 新增 `HomeworkReviewRule` 类型；`HomeworkRecordRow` 补批改字段

---

## 6. 移动端设计

两端 `lib/` 是物理复制的两份，**必须手工同步**。

### 6.1 老师端

`lib/pages/teacher/teacher_home.dart` 的 `_HomeworkRecordsPage`：

- 每条记录的操作区新增「批改」按钮 → `showModalBottomSheet`
- 弹层内容：作答原文、分数 `TextField`（数字键盘，0–100）、评语 `TextField`（多行）、提交按钮
- 已批改的记录显示分数与评语摘要
- 提交调 `TeacherApi.instance.reviewHomework(...)`

### 6.2 学生端

`lib/pages/student/homework_page.dart` 的 `HomeworkDetailPage`：

- 提交信息区块下方新增「老师批改」区块：分数、评语、批改时间
- 未批改显示「老师尚未批改」

### 6.3 API 层

`lib/core/apis.dart`：

- `TeacherApi` 新增 `reviewHomework` / `pendingHomeworkReviews`
- `StudentApi` 无需新增（`homeworkDetail` 已返回含批改字段的 `my_record`）

### 6.4 不做

- admin 档位配置（对齐现有 admin 移动端精简定位）
- 待批改汇总页（从作业完成情况页进入批改）

---

## 7. 错误处理

| 场景 | code | 提示文案 |
|------|------|----------|
| 非 teacher 调用批改 | 403 | 仅老师可执行此操作 |
| 班级不属于该老师 | 403 | 只能操作自己班级的数据 |
| 作业或记录不存在 | 404 | 记录不存在 |
| 该生未提交 | 400 | 学生尚未提交，不可批改 |
| 分数超范围 | 400 | 分数需在 0–100 之间 |
| 档位下限重复 | 400 | 该分数档位已存在 |
| 余额不足回扣 | — | 不报错，扣到 0 为止（见 4.3） |
| 档位表无匹配 | — | 不报错，发 0 积分，仅更新分数与评语 |

前端沿用现有 `message.error(e instanceof Error ? e.message : 'xxx失败')` 模式。

---

## 8. 测试策略

### 8.1 服务端

新增 `tests/test_homework_review.py`（需可连 MySQL，`test_` 前缀隔离，只 INSERT/UPDATE）：

| 用例 | 断言 |
|------|------|
| 批改正常作业 | 分数/评语落库；按档位发积分；流水 `type='review'` |
| 首次批改发分 | 90 分 → +5，`review_points=5` |
| 改分回扣（余额充足） | 90→60 分，delta=-4，余额充足时实扣 4，`review_points`=1 |
| 改分补发为正 | 60→90 分，补发 4 分，`review_points=5` |
| 余额不足扣分 | 余额 2 分、待扣 4 → 实扣 2、不报错、流水记 -2、`review_points=3` |
| 未提交记录批改 | 400 |
| 跨班批改 | 403 |
| 非老师批改 | 403 |
| 档位匹配边界 | 90 分命中 90 档；89 分命中 80 档；59 分无匹配发 0 |
| 重复批改幂等 | 同分再批 → delta=0，**不重复发积分**（流水条数不变） |
| 待批改列表 | 只返回未批改且已提交的记录 |

同步适配现有 `tests/test_classes_homework.py`（`_record_to_dict` 新增字段后相关断言可能需调整）。

### 8.2 Web

- `npm run build`（含 `tsc -b` 类型检查）零错误
- `npm run lint` 仍失败（仓库无 ESLint 配置，已知缺陷，不在本次范围）

### 8.3 移动端

- `flutter analyze` 零错误
- 手工验证批改流程：老师批改 → 学生端可见结果
- `flutter test` 仍只有 config 测试（6 个离线用例）

### 8.4 验收

`python zg-tsp-docs/scripts/acceptance_check.py` 需同步更新，覆盖新增接口。

---

## 9. 文档同步

| 文件 | 改动 |
|------|------|
| `zg-tsp-docs/sys_doc/PRD.md` | 5.3 补「批改」小节；第 7 节接口清单补 5 个接口；4.1 补两张表的建表 SQL；4.2 附近补档位种子说明 |
| `zg-tsp-web/src/api/types.ts` | 新增 `HomeworkReviewRule`；补批改字段 |
| `zg-tsp-docs/sql/init.sql` | 由 `export_ddl` 重新生成 |

---

## 10. 实施顺序

1. **服务端数据层**：`entities.py` 加字段 + 新表 → 迁移脚本 → `export_ddl` → `apply_comments`
2. **服务端接口**：`/homework/review`、`/homework/pending`、三个档位接口 → 积分差额与回扣逻辑
3. **服务端测试**：`tests/test_homework_review.py`
4. **Web 端**：API 层与类型 → 老师端批改 Modal → 待批改页 → 学生端展示 → admin 档位配置
5. **移动端**：android 改动 → 同步到 ios
6. **文档**：PRD、types.ts、init.sql、验收脚本

---

## 11. 已知风险与取舍

| 风险 | 应对 |
|------|------|
| 改分时余额不足导致账实不一致 | 有意为之，不追扣；需在 UI 提示老师「实际扣减 X 分（余额不足，未追扣）」 |
| 行锁是项目首例 | MySQL 唯一目标环境，无 sqlite 兼容负担；需在并发测试中验证 |
| `point_logs.type` 新增 `review` 取值 | 学生端积分明细的类型筛选需同步支持（Web + 移动端） |
| 移动端两端 `lib/` 需手工同步 | 无 CI 校验，实施时逐文件比对 |
| 存量库 ALTER TABLE | 幂等迁移脚本 + `--check` 模式 |
| 独立仓库与快照不同步 | 本次实施须同步到 `../zg-tsp-repos/`（服务实际运行的那份） |
