# 老师端作业审批（批改）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 老师可对学生提交的作业打分数并写评语，分数按可配置档位换算成额外积分（改分时按差额补发/回扣），学生端可见批改结果。

**Architecture:** 在 `homework_records` 表上直接加批改字段（方案 A，一个学生一次作业只有一行记录，改分即 UPDATE），新建 `homework_review_rules` 档位表存「分数下限 → 积分」映射。批改积分走 `point_logs.type='review'`，与提交时自动发的 `homework` 类型隔离；`review_points` 字段记录实际已发放的批改积分，用于算差额。

**Tech Stack:** Python 3.12 / FastAPI 0.115 / SQLAlchemy 2.0 / MySQL 8 · React 18 / Vite 6 / Ant Design 5 / Zustand 5 · Flutter 3.47 / Dart 3.13

**设计文档：** `docs/superpowers/specs/2026-11-04-teacher-homework-review-design.md`

## Global Constraints

- **所有接口全 POST + JSON Body**，参数不进 URL。响应固定 `{code, message, data}`，错误码 0/400/401/403/404/429/500
- **router 里抛 `HTTPException` 时 `detail` 必须是 `{"code": ..., "message": ...}` 字典**，否则 handler 会退化成 `fail(status_code, str(detail))`。每个 router 文件顶部自带 `_bad_request` / `_forbidden` / `_not_found` 私有 helper
- **数据访问只走 `app/db/repo.py`**，SQLAlchemy 2.0 `select()` + `db.scalar()`。Repo 方法只 `db.add()` + `db.flush()`，**不 commit**，commit 由 router 层负责
- **无 Alembic**：`create_all()` 只建缺失的表，**不改已有表结构**。改字段必须显式 ALTER，靠迁移脚本
- **JSON 字段一律用 `Text` 存 JSON 字符串**
- **MySQL 适配**：无真 BOOLEAN，用 `Boolean`（映射 TINYINT(1)）
- **测试直接跑在开发库 `zg_tsp` 上**，不 mock、不用 sqlite。`test_` 前缀 + 随机后缀隔离，**只 INSERT/UPDATE，从不 DELETE/TRUNCATE**
- **移动端 `zg-tsp-android/lib/` 与 `zg-tsp-ios/lib/` 是物理复制的两份**，改任何一份必须手工同步另一份，**无 CI 校验**
- **`scripts/dev.sh` 与 `scripts/build.sh` 的 `REPOS_DIR` 探测顺序是 `../zg-tsp-repos` → `$ROOT`**，默认命中的是独立仓库而不是本快照。构建/跑本快照必须显式 `REPOS_DIR="$PWD"`
- **本次实施须同步到 `/Users/zg/PycharmProjects/zg-tsp-repos/`**（服务实际运行的那份），两边文件保持一致
- 分数范围 `0–100`；积分不设日上限（一个学生一天可能被批改多份作业）
- Web 端 `npm run lint` 必然失败（仓库无 ESLint 配置，已知缺陷，不在本次范围）

---

## 文件结构

**服务端 `zg-tsp-server/`**

| 文件 | 动作 | 职责 |
|------|------|------|
| `app/models/entities.py` | 修改 | `HomeworkRecord` 加 5 个批改字段；新增 `HomeworkReviewRule` 实体 |
| `app/models/constants.py` | 修改 | 新增 `POINT_TYPE_REVIEW = "review"` |
| `app/db/repo.py` | 修改 | `HomeworkReviewRule` 的增删改查；待批改列表查询；批改用的行锁取记录 |
| `app/services/point_service.py` | 修改 | 新增 `award_amount()` / `deduct_amount()` |
| `app/seed/migrate_homework_review.py` | 创建 | 幂等迁移脚本：ALTER 加列 + 建表 + 档位种子 |
| `app/routers/homework.py` | 修改 | `/homework/review`、`/homework/pending` 两个接口；`_record_to_dict` 加批改字段 |
| `app/routers/homework_review_admin.py` | 创建 | 档位配置三个 admin 接口（整组 `require_admin`） |
| `tests/test_homework_review.py` | 创建 | 批改功能测试 |

**Web 端 `zg-tsp-web/`**

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/api/types.ts` | 修改 | `HomeworkReviewRule` 类型；`HomeworkRecordRow` 补批改字段；`PointType` 加 `review` |
| `src/api/classes.ts` | 修改 | `homeworkApi.review` / `homeworkApi.pending` |
| `src/api/parent.ts` | 修改 | 三个档位配置接口（沿用现状：admin 接口混放此文件） |
| `src/components/ReviewModal.tsx` | 创建 | 批改弹窗（老师端两处复用） |
| `src/pages/teacher/HomeworkRecords.tsx` | 修改 | 表格加分数/评语列 + 批改按钮 |
| `src/pages/teacher/HomeworkPending.tsx` | 创建 | 待批改列表页 |
| `src/pages/teacher/Homework.tsx` | 修改 | 顶部加「待批改 N」入口 |
| `src/pages/student/HomeworkDetail.tsx` | 修改 | 显示老师批改结果 |
| `src/pages/admin/Rules.tsx` | 修改 | 下方加「作业批改档位」Card |
| `src/router/index.tsx` | 修改 | 新增 `/teacher/homework/pending` 路由 |

**移动端 `zg-tsp-android/lib/` + `zg-tsp-ios/lib/`（两份同步）**

| 文件 | 动作 | 职责 |
|------|------|------|
| `core/apis.dart` | 修改 | `TeacherApi.reviewHomework` |
| `pages/teacher/teacher_home.dart` | 修改 | 批改入口 + 底部弹层 |
| `pages/student/homework_page.dart` | 修改 | 显示批改结果 |

**文档 `zg-tsp-docs/`**

| 文件 | 动作 | 职责 |
|------|------|------|
| `sql/init.sql` | 重新生成 | `python -m app.seed.export_ddl` |
| `sys_doc/PRD.md` | 修改 | 5.3 补批改小节、第 7 节接口清单、4.1 建表 SQL |
| `scripts/acceptance_check.py` | 修改 | 补新增接口的验收断言 |

---

## Task 1: 数据模型与迁移

**Files:**
- Modify: `zg-tsp-server/app/models/entities.py`
- Modify: `zg-tsp-server/app/models/constants.py`
- Create: `zg-tsp-server/app/seed/migrate_homework_review.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `HomeworkRecord.review_score: int | None`、`review_comment: str | None`、`reviewed_at: datetime | None`、`reviewed_by: int | None`、`review_points: int`
  - `HomeworkReviewRule` 实体：`id / min_score / points / enabled / updated_by / updated_at`
  - `constants.POINT_TYPE_REVIEW = "review"`

- [ ] **Step 1: 在 `constants.py` 新增积分类型常量**

编辑 `zg-tsp-server/app/models/constants.py`，在 `POINT_TYPE_CONSUME = "consume"` 之后追加：

```python
POINT_TYPE_REVIEW = "review"
```

- [ ] **Step 2: 在 `entities.py` 给 `HomeworkRecord` 加批改字段**

编辑 `zg-tsp-server/app/models/entities.py`。把 `HomeworkRecord` 的 `__table_args__` 改为：

```python
    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_homework_student"),
        Index("ix_homework_records_student", "student_id"),
        Index("ix_homework_records_pending", "homework_id", "reviewed_at"),
        {"comment": "作业记录表：学生开始/提交打点与用时统计"},
    )
```

在 `points: Mapped[int] = mapped_column(Integer, default=0, comment="本次获得的积分（读 point_rules）")` 之后追加：

```python
    review_score: Mapped[int | None] = mapped_column(Integer, comment="批改分数 0–100；NULL 表示未批改")
    review_comment: Mapped[str | None] = mapped_column(Text, comment="老师评语")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, comment="批改时间")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="批改老师用户ID")
    review_points: Mapped[int] = mapped_column(Integer, default=0, comment="实际已发放的批改积分（改分时按差额补发/回扣）")
```

- [ ] **Step 3: 在 `entities.py` 新增 `HomeworkReviewRule` 实体**

在 `HomeworkRecord` 类定义结束之后（`# --- checkins ---` 注释之前）插入：

```python
class HomeworkReviewRule(Base):
    """作业批改档位表：分数下限 → 积分的映射（admin 可改）。

    匹配规则：取所有 enabled 且 min_score <= score 的档位中 min_score 最大的一档；
    无匹配则发 0 积分（不报错）。

    与 point_rules 的区别：point_rules 存「一次行为发多少分」的单值规则，
    本表存「分数区间 → 积分」的档位映射，结构不同故独立建表。
    """

    __tablename__ = "homework_review_rules"
    __table_args__ = (
        {"comment": "作业批改档位表：分数下限 → 积分映射，admin 可改"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="档位ID")
    min_score: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, comment="档位分数下限（含）")
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="该档位发放的积分")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用；false 则跳过该档")
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="最后修改人（admin）ID")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="最后修改时间"
    )

    def __repr__(self) -> str:
        return f"<HomeworkReviewRule >= {self.min_score} -> {self.points}分>"
```

- [ ] **Step 4: 写迁移脚本**

创建 `zg-tsp-server/app/seed/migrate_homework_review.py`：

```python
"""作业批改功能数据迁移：新增批改字段 + 建档位表 + 写档位种子。

仓库**无 Alembic**，`Base.metadata.create_all()` 只建缺失的表、
**不修改已有表的结构**，因此新增列必须显式 ALTER。

本脚本**幂等**：已存在的列/表/种子直接跳过，可重复执行。

用法：
    python -m app.seed.migrate_homework_review
    python -m app.seed.migrate_homework_review --check   # 只检查不修改
"""

import argparse

from sqlalchemy import text

from app.db.session import engine

# (列名, MySQL 列定义)
NEW_COLUMNS = [
    ("review_score", "INTEGER NULL COMMENT '批改分数 0–100；NULL 表示未批改'"),
    ("review_comment", "TEXT NULL COMMENT '老师评语'"),
    ("reviewed_at", "DATETIME NULL COMMENT '批改时间'"),
    ("reviewed_by", "INTEGER NULL COMMENT '批改老师用户ID'"),
    ("review_points", "INTEGER NOT NULL DEFAULT 0 COMMENT '实际已发放的批改积分（改分时按差额补发/回扣）"),
]

# (min_score, points) 种子档位
SEED_RULES = [(90, 5), (80, 3), (60, 1)]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS homework_review_rules (
    id          INTEGER      NOT NULL AUTO_INCREMENT,
    min_score   INTEGER      NOT NULL,
    points      INTEGER      NOT NULL DEFAULT 0,
    enabled     TINYINT(1)   DEFAULT 1,
    updated_by  INTEGER      NULL,
    updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_homework_review_rules_min_score (min_score),
    CONSTRAINT fk_homework_review_rules_updated_by FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作业批改档位表：分数下限 → 积分映射，admin 可改'
"""


def _existing_columns(conn) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'homework_records'"
        )
    )
    return {row[0] for row in rows}


def _existing_min_scores(conn) -> set[int]:
    rows = conn.execute(text("SELECT min_score FROM homework_review_rules"))
    return {row[0] for row in rows}


def main(check_only: bool = False) -> None:
    with engine.begin() as conn:
        existing = _existing_columns(conn)
        added: list[str] = []
        for name, ddl in NEW_COLUMNS:
            if name in existing:
                print(f"跳过（已存在）：homework_records.{name}")
                continue
            if check_only:
                print(f"待新增：homework_records.{name}")
                added.append(name)
                continue
            conn.execute(text(f"ALTER TABLE homework_records ADD COLUMN {name} {ddl}"))
            added.append(name)

        # 档位表（IF NOT EXISTS，幂等）
        if check_only:
            print("待建表：homework_review_rules")
        else:
            conn.execute(text(CREATE_TABLE_SQL))

        # 档位种子
        have = _existing_min_scores(conn)
        for min_score, points in SEED_RULES:
            if min_score in have:
                print(f"跳过（已存在）：档位 {min_score}")
                continue
            if check_only:
                print(f"待写入：档位 {min_score} → {points} 分")
                continue
            conn.execute(
                text(
                    "INSERT INTO homework_review_rules (min_score, points, enabled) "
                    "VALUES (:m, :p, 1)"
                ),
                {"m": min_score, "p": points},
            )
            print(f"已写入：档位 {min_score} → {points} 分")

    if added:
        print(f"已新增列：{', '.join(added)}")
    elif not check_only:
        print("无需变更")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="作业批改功能数据迁移")
    parser.add_argument("--check", action="store_true", help="只检查待更新项，不修改")
    args = parser.parse_args()
    main(check_only=args.check)
```

- [ ] **Step 5: 跑迁移脚本（先 --check 再实跑）**

Run:
```bash
cd zg-tsp-server && python -m app.seed.migrate_homework_review --check
```
Expected: 列出 5 个待新增列、待建表、3 个待写入档位

Run:
```bash
cd zg-tsp-server && python -m app.seed.migrate_homework_review
```
Expected: 输出「已新增列：review_score, review_comment, reviewed_at, reviewed_by, review_points」与 3 条「已写入：档位 …」

- [ ] **Step 6: 验证幂等（重复执行应无变更）**

Run:
```bash
cd zg-tsp-server && python -m app.seed.migrate_homework_review
```
Expected: 5 个「跳过（已存在）」+ 3 个「跳过（已存在）」+「无需变更」

- [ ] **Step 7: 补齐字段注释**

Run:
```bash
cd zg-tsp-server && python -m app.seed.apply_comments
```
Expected: 输出「注释已更新：N 个表、M 个字段」（首次运行会有变更，重复运行应为 0）

- [ ] **Step 8: 提交**

```bash
git add zg-tsp-server/app/models/entities.py zg-tsp-server/app/models/constants.py zg-tsp-server/app/seed/migrate_homework_review.py
git commit -m "feat: 作业批改数据模型 —— homework_records 加批改字段 + 新建 homework_review_rules 档位表"
```

---

## Task 2: 积分服务扩展（任意数额发放与回扣）

**Files:**
- Modify: `zg-tsp-server/app/services/point_service.py`

**Interfaces:**
- Consumes: `Repo.get_user_by_id`、`User.total_points`
- Produces:
  - `award_amount(db, student_id, amount, type_, remark=None, operator_id=None) -> int` —— 返回实际发放额
  - `deduct_amount(db, student_id, amount, type_, remark=None, operator_id=None) -> int` —— 返回实际扣减额

- [ ] **Step 1: 写失败的测试**

创建 `zg-tsp-server/tests/test_point_review_amount.py`：

```python
"""批改积分的任意数额发放与回扣（PRD 5.3 作业批改）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

import pytest
from sqlalchemy import select

from app.db.repo import Repo
from app.models.constants import POINT_TYPE_REVIEW, ROLE_STUDENT
from app.models.entities import PointLog


@pytest.fixture
def student_with_points(db, make_user):
    """创建一个带指定余额的学生，返回 (User, 密码)。"""

    def _make(total: int = 100):
        user, pw = make_user(ROLE_STUDENT, "pt")
        user.total_points = total
        db.commit()
        db.refresh(user)
        return user, pw

    return _make


def _logs(db, user_id):
    rows = db.scalars(
        select(PointLog).where(
            PointLog.student_id == user_id,
            PointLog.type == POINT_TYPE_REVIEW,
        )
    ).all()
    return list(rows)


def test_award_amount_adds_points_and_writes_log(db, student_with_points):
    """按指定数额发放积分，写 review 类型流水。"""
    from app.services import point_service

    student, _ = student_with_points(100)
    awarded = point_service.award_amount(
        db, student.id, 5, POINT_TYPE_REVIEW, remark="作业批改：作文", operator_id=1
    )
    db.commit()

    assert awarded == 5
    db.expire_all()
    assert Repo(db).get_user_by_id(student.id).total_points == 105
    logs = _logs(db, student.id)
    assert len(logs) == 1
    assert logs[0].points == 5


def test_award_amount_zero_writes_nothing(db, student_with_points):
    """数额 <= 0 不写流水、不改余额。"""
    from app.services import point_service

    student, _ = student_with_points(100)
    awarded = point_service.award_amount(db, student.id, 0, POINT_TYPE_REVIEW)
    db.commit()

    assert awarded == 0
    db.expire_all()
    assert Repo(db).get_user_by_id(student.id).total_points == 100
    assert _logs(db, student.id) == []


def test_award_amount_rejects_non_student(db, make_user):
    """只能给学生账号发放。"""
    from app.services import point_service
    from app.models.constants import ROLE_TEACHER

    teacher, _ = make_user(ROLE_TEACHER, "pt")
    with pytest.raises(point_service.PointError):
        point_service.award_amount(db, teacher.id, 5, POINT_TYPE_REVIEW)


def test_deduct_amount_within_balance(db, student_with_points):
    """余额充足时全额扣减。"""
    from app.services import point_service

    student, _ = student_with_points(100)
    deducted = point_service.deduct_amount(
        db, student.id, 30, remark="作业批改：改分回扣", operator_id=1
    )
    db.commit()

    assert deducted == 30
    db.expire_all()
    assert Repo(db).get_user_by_id(student.id).total_points == 70
    logs = _logs(db, student.id)
    assert len(logs) == 1
    assert logs[0].points == -30


def test_deduct_amount_stops_at_zero(db, student_with_points):
    """余额不足时扣到 0 为止，不抛异常，记录实际扣减额。"""
    from app.services import point_service

    student, _ = student_with_points(2)
    deducted = point_service.deduct_amount(db, student.id, 4)
    db.commit()

    assert deducted == 2
    db.expire_all()
    assert Repo(db).get_user_by_id(student.id).total_points == 0
    logs = _logs(db, student.id)
    assert len(logs) == 1
    assert logs[0].points == -2


def test_deduct_amount_no_balance_deducts_zero(db, student_with_points):
    """无余额可扣时返回 0，不写流水。"""
    from app.services import point_service

    student, _ = student_with_points(0)
    deducted = point_service.deduct_amount(db, student.id, 4)
    db.commit()

    assert deducted == 0
    db.expire_all()
    assert Repo(db).get_user_by_id(student.id).total_points == 0
    assert _logs(db, student.id) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_point_review_amount.py -q
```
Expected: FAIL —— `AttributeError: module 'app.services.point_service' has no attribute 'award_amount'`

- [ ] **Step 3: 实现 `award_amount` 与 `deduct_amount`**

编辑 `zg-tsp-server/app/services/point_service.py`，在 `consume` 函数之后插入：

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

    与 `award` 的区别：`award` 的数额取自 `point_rules` 表，本方法直接指定数额，
    用于「分数换算积分」这类数额由业务数据决定的场景（PRD 5.3 作业批改）。

    amount <= 0 时直接返回 0，不写流水。同步累加 `users.total_points`。
    """
    if amount <= 0:
        return 0

    user = Repo(db).get_user_by_id(student_id)
    if user is None or user.role != ROLE_STUDENT:
        raise PointError("仅可为学生账号发放积分")

    db.add(
        PointLog(
            student_id=student_id,
            type=type_,
            points=amount,
            remark=remark,
            operator_id=operator_id,
            log_date=today(),
        )
    )
    user.total_points += amount
    db.flush()
    return amount


def deduct_amount(
    db: Session,
    student_id: int,
    amount: int,
    type_: str,
    remark: str | None = None,
    operator_id: int | None = None,
) -> int:
    """回扣积分（不经 point_rules）。

    与 `consume` 的区别：`consume` 余额不足时抛 `PointError`，
    本方法**扣到 0 为止**、不抛异常 —— 老师改低分数时不该被学生余额卡住
    （PRD 5.3 作业批改）。欠额不追扣。

    返回实际扣减额；无余额可扣时返回 0。
    """
    if amount <= 0:
        return 0

    user = Repo(db).get_user_by_id(student_id)
    if user is None or user.role != ROLE_STUDENT:
        raise PointError("仅可为学生账号扣减积分")

    actual = min(amount, user.total_points)
    if actual <= 0:
        return 0

    db.add(
        PointLog(
            student_id=student_id,
            type=type_,
            points=-actual,  # 流水记负数
            remark=remark,
            operator_id=operator_id,
            log_date=today(),
        )
    )
    user.total_points -= actual
    db.flush()
    return actual
```

同时把 `point_service.py` 顶部的 import 改为：

```python
from app.models.constants import POINT_TYPE_CONSUME, POINT_TYPE_REVIEW, ROLE_STUDENT
```

（原 import 是 `from app.models.constants import POINT_TYPE_CONSUME, ROLE_STUDENT`。）

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_point_review_amount.py -q
```
Expected: PASS —— 6 passed

- [ ] **Step 5: 提交**

```bash
git add zg-tsp-server/app/services/point_service.py zg-tsp-server/tests/test_point_review_amount.py
git commit -m "feat: 积分服务新增 award_amount / deduct_amount —— 支持任意数额发放与扣到 0 为止的回扣"
```

---

## Task 3: 数据层 —— 档位与待批改查询

**Files:**
- Modify: `zg-tsp-server/app/db/repo.py`

**Interfaces:**
- Consumes: `HomeworkReviewRule` 实体、`HomeworkRecord` 新字段
- Produces:
  - `Repo.list_review_rules() -> list[HomeworkReviewRule]` —— 按 min_score 升序
  - `Repo.get_review_rule_by_min_score(min_score: int) -> HomeworkReviewRule | None`
  - `Repo.add_review_rule(rule: HomeworkReviewRule) -> HomeworkReviewRule`
  - `Repo.match_review_points(score: int) -> int` —— 匹配档位返回积分，无匹配返回 0
  - `Repo.get_homework_record_for_update(homework_id: int, student_id: int) -> HomeworkRecord | None` —— 加行锁
  - `Repo.list_pending_reviews(teacher_id: int, page: int, size: int) -> tuple[list[dict], int]` —— 待批改列表

- [ ] **Step 1: 在 `repo.py` 加档位表方法**

编辑 `zg-tsp-server/app/db/repo.py`。在 `# ---------------- 作业（PRD 5.3） ----------------` 段落之后、`# ---------------- 签到（PRD 5.4） ----------------` 之前插入：

```python
    # ---------------- 作业批改档位（PRD 5.3） ----------------

    def add_review_rule(self, rule: HomeworkReviewRule) -> HomeworkReviewRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def list_review_rules(self) -> list[HomeworkReviewRule]:
        return list(
            self.db.scalars(
                select(HomeworkReviewRule).order_by(HomeworkReviewRule.min_score.desc())
            )
        )

    def get_review_rule_by_min_score(self, min_score: int) -> HomeworkReviewRule | None:
        return self.db.scalar(
            select(HomeworkReviewRule).where(HomeworkReviewRule.min_score == min_score)
        )

    def get_review_rule_by_id(self, rule_id: int) -> HomeworkReviewRule | None:
        return self.db.get(HomeworkReviewRule, rule_id)

    def match_review_points(self, score: int) -> int:
        """按分数匹配档位，返回该档积分；无匹配返回 0。

        取所有 enabled 且 min_score <= score 的档位中 min_score 最大的一档。
        """
        rule = self.db.scalar(
            select(HomeworkReviewRule)
            .where(
                HomeworkReviewRule.enabled.is_(True),
                HomeworkReviewRule.min_score <= score,
            )
            .order_by(HomeworkReviewRule.min_score.desc())
            .limit(1)
        )
        return rule.points if rule else 0
```

- [ ] **Step 2: 在 `repo.py` 加行锁取记录的方法**

在 `get_homework_record` 方法之后插入：

```python
    def get_homework_record_for_update(
        self, homework_id: int, student_id: int
    ) -> HomeworkRecord | None:
        """取记录并加行锁（SELECT ... FOR UPDATE）。

        批改作业时用，防止两个老师同时批改同一份导致积分重复发放
        （PRD 5.3）。仅 MySQL 生效。
        """
        return self.db.scalar(
            select(HomeworkRecord)
            .where(
                HomeworkRecord.homework_id == homework_id,
                HomeworkRecord.student_id == student_id,
            )
            .with_for_update()
        )
```

- [ ] **Step 3: 在 `repo.py` 加待批改列表查询**

在 `count_submitted_records` 方法之后插入：

```python
    def list_pending_reviews(
        self, teacher_id: int, page: int = 1, size: int = 20
    ) -> tuple[list[dict], int]:
        """待批改列表：该老师所有班级的「已提交但未批改」记录（PRD 5.3）。

        返回 (当前页行, 总数)。每行含学生名、作业标题、提交信息与异常标记。
        """
        base = (
            select(HomeworkRecord, Homework, User)
            .join(Homework, Homework.id == HomeworkRecord.homework_id)
            .join(User, User.id == HomeworkRecord.student_id)
            .join(Class, Class.id == Homework.class_id)
            .where(
                Class.teacher_id == teacher_id,
                HomeworkRecord.submit_time.isnot(None),
                HomeworkRecord.reviewed_at.is_(None),
            )
        )
        count_stmt = (
            select(func.count())
            .select_from(HomeworkRecord)
            .join(Homework, Homework.id == HomeworkRecord.homework_id)
            .join(Class, Class.id == Homework.class_id)
            .where(
                Class.teacher_id == teacher_id,
                HomeworkRecord.submit_time.isnot(None),
                HomeworkRecord.reviewed_at.is_(None),
            )
        )
        total = self.db.scalar(count_stmt) or 0
        stmt = (
            base.order_by(HomeworkRecord.submit_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = []
        for rec, hw, stu in self.db.execute(stmt).all():
            rows.append({
                "homework_id": hw.id,
                "homework_title": hw.title,
                "student_id": stu.id,
                "student_name": stu.nickname or stu.username,
                "username": stu.username,
                "submit_time": rec.submit_time.isoformat() if rec.submit_time else None,
                "duration_minutes": rec.duration_minutes,
                "file_url": rec.file_url,
                "text_content": rec.text_content,
                # 用时 <1 分钟标记异常（PRD 5.3）
                "suspicious": bool(
                    rec.duration_minutes is not None and rec.duration_minutes < 1
                ),
            })
        return rows, total
```

- [ ] **Step 4: 补 `repo.py` 的 import**

编辑 `zg-tsp-server/app/db/repo.py` 顶部的 entities import，把

```python
from app.models.entities import (
    AdminLog,
    Article,
    Checkin,
    Class,
    ...
)
```

改为在同一个 import 列表中补入 `HomeworkReviewRule`（按字母序插入，保持该列表已有排序风格）。若该文件当前是单行 import，按同样方式加 `HomeworkReviewRule`。

- [ ] **Step 5: 跑现有作业测试确认没破坏**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_classes_homework.py -q
```
Expected: PASS —— 26 passed

- [ ] **Step 6: 提交**

```bash
git add zg-tsp-server/app/db/repo.py
git commit -m "feat: 数据层新增档位表读写、行锁取记录、待批改列表查询"
```

---

## Task 4: 批改与待批改接口

**Files:**
- Modify: `zg-tsp-server/app/routers/homework.py`

**Interfaces:**
- Consumes: `Repo.get_homework_record_for_update`、`Repo.match_review_points`、`point_service.award_amount` / `deduct_amount`、`Repo.list_pending_reviews`
- Produces:
  - `POST /homework/review` → `{record, points_delta, awarded_points}`
  - `POST /homework/pending` → `{list, total, page, size}`
  - `_record_to_dict()` 增加 `review_score` / `review_comment` / `reviewed_at` / `review_points`

- [ ] **Step 1: 写失败的测试**

创建 `zg-tsp-server/tests/test_homework_review.py`：

```python
"""老师端作业批改（PRD 5.3）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

from datetime import datetime, timedelta

import pytest

from app.db.repo import Repo
from app.models.constants import (
    HOMEWORK_SUBMITTED,
    POINT_TYPE_REVIEW,
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.services.point_rule_service import rule_service


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


def post_form(client, path, data=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, data=data or {}, headers=headers)


@pytest.fixture(autouse=True)
def _clear_cache():
    rule_service.invalidate()
    yield
    rule_service.invalidate()


@pytest.fixture
def set_rule(client, admin_token, db):
    def _set(rule_key: str, **fields) -> None:
        r = post(client, "/admin/rules/update", {"rule_key": rule_key, **fields}, token=admin_token)
        assert r.status_code == 200, r.text
        db.rollback()
        db.expire_all()
        rule_service.invalidate(rule_key)

    return _set


@pytest.fixture
def seed_review_rules(db):
    """确保档位表里有 90→5 / 80→3 / 60→1 三档种子。

    这些用例断言具体的档位积分值，因此档位必须存在且值正确。
    迁移脚本已写入种子，此夹具是兜底（迁移未跑或种子被改动时）。
    """
    from app.db.repo import Repo
    from app.models.entities import HomeworkReviewRule

    repo = Repo(db)
    for min_score, points in [(90, 5), (80, 3), (60, 1)]:
        rule = repo.get_review_rule_by_min_score(min_score)
        if rule is None:
            repo.add_review_rule(
                HomeworkReviewRule(min_score=min_score, points=points, enabled=True)
            )
        else:
            rule.points = points
            rule.enabled = True
    db.commit()
    db.expire_all()


@pytest.fixture
def klass_with_student(make_class, make_user, db):
    """(班级, 班主任, 班主任密码, 学生, 学生密码)"""
    klass, teacher, tpw = make_class("批改班")
    student, spw = make_user(ROLE_STUDENT, "hr")
    student.class_id = klass.id
    db.commit()
    return klass, teacher, tpw, student, spw


@pytest.fixture
def submitted_homework(client, login, klass_with_student, set_rule, seed_review_rules):
    """老师布置作业、学生已提交，返回 (homework_id, 老师token, 学生对象, 学生token)。

    依赖 `seed_review_rules` 保证档位表有 90→5 / 80→3 / 60→1 三档。
    """
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student

    hw_id = post(
        client,
        "/homework/create",
        {
            "class_id": klass.id,
            "title": "待批改作业",
            "deadline": (datetime.now() + timedelta(days=1)).isoformat(),
        },
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    stu_token = login(student, spw)
    post(client, "/homework/start", {"homework_id": hw_id}, token=stu_token)
    post_form(
        client,
        "/homework/submit",
        data={"homework_id": hw_id, "text_content": "我的答案"},
        token=stu_token,
    )
    return hw_id, login(teacher, tpw), student, stu_token


def test_review_scores_and_writes_comment(client, login, submitted_homework, refresh, db):
    """批改：分数与评语落库，按 90 分档发 5 分积分。"""
    hw_id, teacher_token, student, _ = submitted_homework

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90, "comment": "很棒"},
        token=teacher_token,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["record"]["review_score"] == 90
    assert data["record"]["review_comment"] == "很棒"
    assert data["record"]["review_points"] == 5
    assert data["awarded_points"] == 5

    refresh()
    assert Repo(db).get_user_by_id(student.id).total_points == 10 + 5  # 提交发的 10 + 批改发的 5


def test_review_reviewed_at_and_by_set(client, login, submitted_homework, refresh, db):
    """批改后写入批改时间与批改人。"""
    hw_id, teacher_token, student, _ = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 85},
        token=teacher_token,
    )

    refresh()
    rec = Repo(db).get_homework_record(hw_id, student.id)
    assert rec.reviewed_at is not None
    assert rec.reviewed_by is not None


def test_review_lower_score_deducts_points(client, login, submitted_homework, refresh, db):
    """改低分：按差额回扣（余额充足时全额扣）。"""
    hw_id, teacher_token, student, _ = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=teacher_token,
    )
    refresh()
    balance_after_first = Repo(db).get_user_by_id(student.id).total_points
    assert balance_after_first == 15

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 60},
        token=teacher_token,
    )
    assert r.status_code == 200, r.text
    # 90 档 5 分 → 60 档 1 分，差额 -4
    assert r.json()["data"]["points_delta"] == -4
    assert r.json()["data"]["awarded_points"] == -4  # 余额充足，全额扣回

    refresh()
    assert Repo(db).get_user_by_id(student.id).total_points == 11
    rec = Repo(db).get_homework_record(hw_id, student.id)
    assert rec.review_score == 60
    assert rec.review_points == 1


def test_review_higher_score_adds_difference(client, login, submitted_homework, refresh, db):
    """改高分：按差额补发。"""
    hw_id, teacher_token, student, _ = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 60},
        token=teacher_token,
    )
    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=teacher_token,
    )
    # 60 档 1 分 → 90 档 5 分，差额 +4
    assert r.json()["data"]["points_delta"] == 4

    refresh()
    assert Repo(db).get_user_by_id(student.id).total_points == 10 + 5


def test_review_same_score_does_not_award_again(client, login, submitted_homework, refresh, db):
    """同分重复批改：幂等，不重复发积分。"""
    hw_id, teacher_token, student, _ = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=teacher_token,
    )
    refresh()
    balance = Repo(db).get_user_by_id(student.id).total_points

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90, "comment": "再看看"},
        token=teacher_token,
    )
    assert r.json()["data"]["points_delta"] == 0

    refresh()
    assert Repo(db).get_user_by_id(student.id).total_points == balance


def test_review_insufficient_balance_deducts_to_zero(client, login, submitted_homework, refresh, db):
    """余额不足时扣到 0 为止，不报错，流水记实际扣减额。"""
    hw_id, teacher_token, student, _ = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=teacher_token,
    )
    refresh()
    # 把学生积分花到只剩 2 分
    user = Repo(db).get_user_by_id(student.id)
    user.total_points = 2
    db.commit()
    db.expire_all()

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 60},
        token=teacher_token,
    )
    assert r.status_code == 200, r.text
    # awarded_points 是净变动：负数表示实扣；余额不足时只扣到 2
    assert r.json()["data"]["awarded_points"] == -2
    # points_delta 是规则层面的应扣额（不受余额影响）
    assert r.json()["data"]["points_delta"] == -4

    refresh()
    assert Repo(db).get_user_by_id(student.id).total_points == 0
    rec = Repo(db).get_homework_record(hw_id, student.id)
    assert rec.review_points == 3  # 5 - 2


def test_review_not_submitted_rejected(client, login, klass_with_student):
    """未提交的记录不可批改。"""
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "未交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=login(teacher, tpw),
    )
    assert r.status_code == 400
    assert "尚未提交" in r.json()["message"]


def test_review_other_class_forbidden(client, login, make_user, make_class, klass_with_student):
    """不能批改别人班的作业。"""
    klass, teacher, tpw, student, _ = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "越权批改", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]
    other, opw = make_user(ROLE_TEACHER, "oo")

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=login(other, opw),
    )
    assert r.status_code == 403


def test_review_student_forbidden(client, login, submitted_homework):
    """学生不可批改。"""
    hw_id, _, student, stu_token = submitted_homework

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=stu_token,
    )
    assert r.status_code == 403


def test_review_score_out_of_range_rejected(client, login, submitted_homework):
    """分数超出 0–100 被拒。"""
    hw_id, teacher_token, student, _ = submitted_homework

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 101},
        token=teacher_token,
    )
    assert r.status_code == 400


def test_review_below_lowest_tier_awards_zero(client, login, submitted_homework, refresh, db):
    """低于最低档位（60）时不发积分，但分数与评语仍落库。"""
    hw_id, teacher_token, student, _ = submitted_homework

    r = post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 30, "comment": "再努力"},
        token=teacher_token,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["awarded_points"] == 0

    refresh()
    rec = Repo(db).get_homework_record(hw_id, student.id)
    assert rec.review_score == 30
    assert rec.review_points == 0
    assert Repo(db).get_user_by_id(student.id).total_points == 10  # 只有提交时发的 10 分


def test_pending_lists_unreviewed_only(client, login, submitted_homework, refresh):
    """待批改列表只含已提交且未批改的记录。"""
    hw_id, teacher_token, student, _ = submitted_homework

    r = post(client, "/homework/pending", {"page": 1, "size": 20}, token=teacher_token)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] == 1
    row = data["list"][0]
    assert row["student_id"] == student.id
    assert row["homework_id"] == hw_id
    assert row["student_name"]

    # 批改后应从列表消失
    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 90},
        token=teacher_token,
    )
    refresh()
    r2 = post(client, "/homework/pending", {"page": 1, "size": 20}, token=teacher_token)
    assert r2.json()["data"]["total"] == 0


def test_pending_empty_for_new_teacher(client, login, make_user):
    """新老师没有待批改记录。"""
    teacher, tpw = make_user(ROLE_TEACHER, "pn")
    r = post(client, "/homework/pending", {"page": 1, "size": 20}, token=login(teacher, tpw))
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


def test_student_sees_review_result(client, login, submitted_homework):
    """学生端能看到老师的批改结果。"""
    hw_id, teacher_token, student, stu_token = submitted_homework

    post(
        client,
        "/homework/review",
        {"homework_id": hw_id, "student_id": student.id, "score": 88, "comment": "继续加油"},
        token=teacher_token,
    )

    r = post(client, "/homework/detail", {"homework_id": hw_id}, token=stu_token)
    assert r.status_code == 200
    rec = r.json()["data"]["homework"]["my_record"]
    assert rec["review_score"] == 88
    assert rec["review_comment"] == "继续加油"
    assert rec["reviewed_at"] is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_homework_review.py -q
```
Expected: FAIL —— 全部 404（接口未实现）

- [ ] **Step 3: 在 `homework.py` 扩展 `_record_to_dict`**

编辑 `zg-tsp-server/app/routers/homework.py`，在 `_record_to_dict` 函数的 `"suspicious": ...` 之后追加：

```python
        # 老师批改结果（PRD 5.3）
        "review_score": r.review_score,
        "review_comment": r.review_comment,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_points": r.review_points,
```

- [ ] **Step 4: 在 `homework.py` 加请求模型**

在 `class HomeworkIdRequest(BaseModel):` 之后追加：

```python
class HomeworkReviewRequest(BaseModel):
    """老师批改作业（PRD 5.3）。"""

    homework_id: int
    student_id: int
    score: int = Field(..., ge=0, le=100)
    comment: str | None = Field(None, max_length=2000)


class HomeworkPendingRequest(BaseModel):
    """待批改列表（PRD 5.3）。"""

    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)
```

- [ ] **Step 5: 在 `homework.py` 实现批改接口**

在 `@router.post("/delete")` 之前插入：

```python
@router.post("/review")
async def review_homework(
    req: HomeworkReviewRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师批改作业：打分 + 评语，积分按差额补发/回扣（PRD 5.3）。

    积分口径：`target` = 新分数匹配的档位积分；`granted` = 该记录已发放的
    批改积分；差额为正则补发，为负则回扣（余额不足时扣到 0 为止）。
    """
    _require_teacher(teacher)

    repo = Repo(db)
    hw = repo.get_homework_by_id(req.homework_id)
    if not hw:
        raise _not_found("作业不存在")
    _own_class_or_403(db, teacher, hw.class_id)

    # 行锁：防止两个老师同时批改同一份导致积分重复发放
    record = repo.get_homework_record_for_update(req.homework_id, req.student_id)
    if not record:
        raise _not_found("记录不存在")
    if record.submit_time is None:
        raise _bad_request("学生尚未提交，不可批改")

    target = repo.match_review_points(req.score)
    granted = record.review_points or 0
    delta = target - granted

    from app.services import point_service

    awarded = 0
    if delta > 0:
        awarded = point_service.award_amount(
            db,
            record.student_id,
            delta,
            POINT_TYPE_REVIEW,
            remark=f"作业批改：{hw.title}",
            operator_id=teacher.id,
        )
    elif delta < 0:
        awarded = -point_service.deduct_amount(
            db,
            record.student_id,
            -delta,
            POINT_TYPE_REVIEW,
            remark=f"作业批改改分：{hw.title}",
            operator_id=teacher.id,
        )

    record.review_score = req.score
    record.review_comment = req.comment
    record.reviewed_at = datetime.now()
    record.reviewed_by = teacher.id
    # awarded 是**净变动**（正=实发，负=实扣），故直接相加。
    # delta<0 且余额不足时 |awarded| < |delta|，此时 review_points 会大于
    # 新分数对应的目标积分 —— 这是「扣到 0 为止、不追扣」的既定语义。
    record.review_points = granted + awarded

    db.commit()
    db.refresh(record)

    return ok({
        "record": _record_to_dict(record),
        "points_delta": delta,
        "awarded_points": awarded,
    })
```

**两个返回字段的语义**：

- `points_delta` —— 目标差额（`target - granted`）。正=应补发，负=应回扣。这是**规则层面**的差额，与余额无关
- `awarded_points` —— 实际积分**净变动**。正=实发，负=实扣。余额不足时其绝对值小于 `|points_delta|`

举例：首次批 90 分发 5 分（`review_points=5`），学生花到只剩 2 分，改成 60 分 → `delta = 1 - 5 = -4`（应扣 4），但余额只有 2 → `awarded_points = -2`（实扣 2），`review_points = 5 + (-2) = 3`。

- [ ] **Step 6: 在 `homework.py` 实现待批改列表接口**

在 `@router.post("/review")` 之后插入：

```python
@router.post("/pending")
async def pending_reviews(
    req: HomeworkPendingRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师查看待批改清单（PRD 5.3）：已提交但未批改的作业。"""
    _require_teacher(teacher)

    rows, total = Repo(db).list_pending_reviews(teacher.id, req.page, req.size)
    return ok({
        "list": rows,
        "total": total,
        "page": req.page,
        "size": req.size,
    })
```

- [ ] **Step 7: 补 `homework.py` 的 import**

编辑 `zg-tsp-server/app/routers/homework.py`，把 constants import 改为：

```python
from app.models.constants import (
    HOMEWORK_DOING,
    HOMEWORK_LATE,
    HOMEWORK_NOT_STARTED,
    HOMEWORK_SUBMITTED,
    POINT_TYPE_HOMEWORK,
    POINT_TYPE_REVIEW,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
```

- [ ] **Step 8: 跑测试确认通过**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_homework_review.py -q
```
Expected: PASS —— 13 passed

- [ ] **Step 9: 跑全部服务端测试确认没回归**

Run:
```bash
cd zg-tsp-server && python -m pytest -q
```
Expected: 全部 PASS（含新增的 19 个用例）

- [ ] **Step 10: 提交**

```bash
git add zg-tsp-server/app/routers/homework.py zg-tsp-server/tests/test_homework_review.py
git commit -m "feat: 作业批改接口 —— /homework/review 积分差额补发 + /homework/pending 待批改列表"
```

---

## Task 5: 档位配置接口（admin）

**Files:**
- Create: `zg-tsp-server/app/routers/homework_review_admin.py`
- Modify: `zg-tsp-server/app/main.py`

**Interfaces:**
- Consumes: `Repo.list_review_rules` / `get_review_rule_by_id` / `get_review_rule_by_min_score` / `add_review_rule`
- Produces:
  - `POST /admin/homework-review-rules/list` → `{list, total}`
  - `POST /admin/homework-review-rules/update` → `{rule}`
  - `POST /admin/homework-review-rules/create` → `{rule}`

- [ ] **Step 1: 写失败的测试**

创建 `zg-tsp-server/tests/test_homework_review_rules.py`：

```python
"""作业批改档位配置（admin，PRD 5.8.3 同类配置）。"""

import pytest


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


@pytest.fixture
def seed_rules(db):
    """确保库里有 90/80/60 三档种子，返回 (min_score -> points) 字典。"""
    from app.db.repo import Repo
    from app.models.entities import HomeworkReviewRule

    repo = Repo(db)
    result = {}
    for min_score, points in [(90, 5), (80, 3), (60, 1)]:
        rule = repo.get_review_rule_by_min_score(min_score)
        if rule is None:
            rule = repo.add_review_rule(
                HomeworkReviewRule(min_score=min_score, points=points, enabled=True)
            )
            db.commit()
        result[min_score] = rule.points
    db.expire_all()
    return result


def test_list_rules_requires_admin(client, admin_token, seed_rules):
    """admin 可列出档位。"""
    r = post(client, "/admin/homework-review-rules/list", token=admin_token)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] >= 3
    mins = [row["min_score"] for row in data["list"]]
    assert 90 in mins


def test_list_rules_forbidden_for_teacher(client, login, make_user):
    """老师不可访问档位配置。"""
    from app.models.constants import ROLE_TEACHER

    teacher, pw = make_user(ROLE_TEACHER, "rr")
    r = post(client, "/admin/homework-review-rules/list", token=login(teacher, pw))
    assert r.status_code == 403


def test_create_rule(client, admin_token, seed_rules, db):
    """admin 可新增档位。"""
    from app.db.repo import Repo

    r = post(
        client,
        "/admin/homework-review-rules/create",
        {"min_score": 95, "points": 8},
        token=admin_token,
    )
    assert r.status_code == 200, r.text
    rule = r.json()["data"]["rule"]
    assert rule["min_score"] == 95
    assert rule["points"] == 8
    assert rule["enabled"] is True


def test_create_rule_duplicate_min_score_rejected(client, admin_token, seed_rules):
    """档位下限唯一，重复则 400。"""
    r = post(
        client,
        "/admin/homework-review-rules/create",
        {"min_score": 90, "points": 99},
        token=admin_token,
    )
    assert r.status_code == 400
    assert "已存在" in r.json()["message"]


def test_create_rule_negative_points_rejected(client, admin_token, seed_rules):
    """积分值不能为负。"""
    r = post(
        client,
        "/admin/homework-review-rules/create",
        {"min_score": 50, "points": -1},
        token=admin_token,
    )
    assert r.status_code == 400


def test_update_rule_points(client, admin_token, seed_rules, db):
    """admin 可改档位积分。

    用**非种子档位**（95 分）做修改，避免污染 90/80/60 三档种子 ——
    Task 4 的批改测试断言 90 分 = +5 分，改了种子会让它失败。
    """
    from app.db.repo import Repo
    from app.models.entities import HomeworkReviewRule

    repo = Repo(db)
    rule = repo.get_review_rule_by_min_score(95)
    if rule is None:
        rule = repo.add_review_rule(
            HomeworkReviewRule(min_score=95, points=9, enabled=True)
        )
        db.commit()
        db.expire_all()
        rule = repo.get_review_rule_by_min_score(95)

    r = post(
        client,
        "/admin/homework-review-rules/update",
        {"id": rule.id, "points": 7},
        token=admin_token,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["rule"]["points"] == 7


def test_update_rule_disable(client, admin_token, seed_rules, db):
    """admin 可停用档位。

    同样用非种子档位（85 分），避免停用 80 档影响其他测试的匹配结果。
    """
    from app.db.repo import Repo
    from app.models.entities import HomeworkReviewRule

    repo = Repo(db)
    rule = repo.get_review_rule_by_min_score(85)
    if rule is None:
        rule = repo.add_review_rule(
            HomeworkReviewRule(min_score=85, points=2, enabled=True)
        )
        db.commit()
        db.expire_all()
        rule = repo.get_review_rule_by_min_score(85)

    r = post(
        client,
        "/admin/homework-review-rules/update",
        {"id": rule.id, "enabled": False},
        token=admin_token,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["rule"]["enabled"] is False


def test_update_rule_not_found(client, admin_token, seed_rules):
    """改不存在的档位 → 404。"""
    r = post(
        client,
        "/admin/homework-review-rules/update",
        {"id": 999999, "points": 3},
        token=admin_token,
    )
    assert r.status_code == 404


def test_disabled_rule_not_matched(client, admin_token, seed_rules, db, refresh):
    """停用的档位不参与匹配。

    用非种子档位（95 分）验证：停用后 95 分落到 90 档（5 分），而非 95 档。
    """
    from app.db.repo import Repo
    from app.models.entities import HomeworkReviewRule

    repo = Repo(db)
    rule = repo.get_review_rule_by_min_score(95)
    if rule is None:
        rule = repo.add_review_rule(
            HomeworkReviewRule(min_score=95, points=9, enabled=True)
        )
        db.commit()
        db.expire_all()
        rule = repo.get_review_rule_by_min_score(95)

    post(
        client,
        "/admin/homework-review-rules/update",
        {"id": rule.id, "enabled": False},
        token=admin_token,
    )
    db.expire_all()
    # 95 分不再命中已停用的 95 档，落到 90 档
    assert Repo(db).match_review_points(95) == 5
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_homework_review_rules.py -q
```
Expected: FAIL —— 全部 404（router 未注册）

- [ ] **Step 3: 创建档位配置 router**

创建 `zg-tsp-server/app/routers/homework_review_admin.py`：

```python
"""作业批改档位配置接口（admin）。

档位表 `homework_review_rules` 存「分数下限 → 积分」映射，admin 可改。
与 `point_rules` 的分工：point_rules 是单值规则（一次行为发多少分），
本表是档位区间映射（PRD 5.3 作业批改）。

修改立即生效（无缓存层 —— 匹配时直接查库）。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.entities import HomeworkReviewRule, User
from app.utils.deps import require_admin
from app.utils.response import CODE_BAD_REQUEST, CODE_NOT_FOUND, ok

router = APIRouter(
    prefix="/admin/homework-review-rules",
    tags=["作业批改档位"],
    dependencies=[Depends(require_admin)],
)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


# ---------------- 出入参 ----------------


class ReviewRuleCreateRequest(BaseModel):
    min_score: int = Field(..., ge=0, le=100)
    points: int = Field(..., ge=0, le=10000)


class ReviewRuleUpdateRequest(BaseModel):
    id: int
    points: int | None = Field(None, ge=0, le=10000)
    enabled: bool | None = None


# ---------------- 工具 ----------------


def _rule_to_dict(r: HomeworkReviewRule) -> dict:
    return {
        "id": r.id,
        "min_score": r.min_score,
        "points": r.points,
        "enabled": bool(r.enabled),
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ---------------- 接口 ----------------


@router.post("/list")
async def review_rules_list(db: Session = Depends(get_db)):
    """列出全部档位（按分数下限从高到低）。"""
    rules = Repo(db).list_review_rules()
    return ok({"list": [_rule_to_dict(r) for r in rules], "total": len(rules)})


@router.post("/create")
async def review_rule_create(
    req: ReviewRuleCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新增档位。`min_score` 唯一。"""
    repo = Repo(db)
    if repo.get_review_rule_by_min_score(req.min_score) is not None:
        raise _bad_request(f"该分数档位已存在：{req.min_score}")

    rule = repo.add_review_rule(
        HomeworkReviewRule(
            min_score=req.min_score,
            points=req.points,
            enabled=True,
            updated_by=admin.id,
        )
    )
    db.commit()
    db.refresh(rule)
    return ok({"rule": _rule_to_dict(rule)})


@router.post("/update")
async def review_rule_update(
    req: ReviewRuleUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新档位（积分值 / 启停）。未传的字段保持不变。"""
    repo = Repo(db)
    rule = repo.get_review_rule_by_id(req.id)
    if not rule:
        raise _not_found(f"档位 {req.id} 不存在")

    if req.points is not None:
        rule.points = req.points
    if req.enabled is not None:
        rule.enabled = req.enabled
    rule.updated_by = admin.id

    db.commit()
    db.refresh(rule)
    return ok({"rule": _rule_to_dict(rule)})
```

- [ ] **Step 4: 注册 router**

编辑 `zg-tsp-server/app/main.py`，找到 router 注册处（形如 `app.include_router(homework.router)` 的一组），按现有 import 与注册的风格补两行：

```python
from app.routers import homework_review_admin
```

```python
app.include_router(homework_review_admin.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run:
```bash
cd zg-tsp-server && python -m pytest tests/test_homework_review_rules.py -q
```
Expected: PASS —— 9 passed

- [ ] **Step 6: 跑全部服务端测试确认没回归**

Run:
```bash
cd zg-tsp-server && python -m pytest -q
```
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add zg-tsp-server/app/routers/homework_review_admin.py zg-tsp-server/app/main.py zg-tsp-server/tests/test_homework_review_rules.py
git commit -m "feat: 作业批改档位配置接口 —— admin 可增改启停分数档位"
```

---

## Task 6: Web 端类型与 API 层

**Files:**
- Modify: `zg-tsp-web/src/api/types.ts`
- Modify: `zg-tsp-web/src/api/classes.ts`
- Modify: `zg-tsp-web/src/api/parent.ts`

**Interfaces:**
- Consumes: 服务端 Task 4 / Task 5 的接口
- Produces:
  - `type HomeworkReviewRule = { id, min_score, points, enabled, updated_at }`
  - `homeworkApi.review(homeworkId, studentId, score, comment)` → `{ record, points_delta, awarded_points }`
  - `homeworkApi.pending(page, size)` → `{ list, total, page, size }`
  - `reviewRuleApi.list()` / `.create(minScore, points)` / `.update(id, fields)`
  - `HomeworkRecordRow` 增补 `review_score` / `review_comment` / `reviewed_at` / `review_points`
  - `PointType` 增补 `'review'`

- [ ] **Step 1: 补 `types.ts` 类型**

编辑 `zg-tsp-web/src/api/types.ts`。把

```typescript
export type PointType = 'checkin' | 'homework' | 'reading' | 'game' | 'consume'
```

改为

```typescript
export type PointType = 'checkin' | 'homework' | 'reading' | 'game' | 'consume' | 'review'
```

在 `HomeworkRecordRow` 接口的 `suspicious?: boolean` 之后追加：

```typescript
  /** 老师批改分数 0–100；null/undefined 表示未批改 */
  review_score?: number | null
  /** 老师评语 */
  review_comment?: string | null
  /** 批改时间 */
  reviewed_at?: string | null
  /** 实际已发放的批改积分 */
  review_points?: number
```

在 `HomeworkRecord` 接口（第 65 行，学生端 `my_record` 用的类型）的 `suspicious: boolean` 之后追加**同样的四个字段**：

```typescript
  /** 老师批改分数 0–100；null 表示未批改 */
  review_score?: number | null
  /** 老师评语 */
  review_comment?: string | null
  /** 批改时间 */
  reviewed_at?: string | null
  /** 实际已发放的批改积分 */
  review_points?: number
```

在 `HomeworkRecordRow` 接口之后追加：

```typescript
/** 作业批改档位（admin 可配） */
export interface HomeworkReviewRule {
  id: number
  /** 档位分数下限（含） */
  min_score: number
  /** 该档位发放的积分 */
  points: number
  enabled: boolean
  updated_at: string | null
}

/** 待批改列表行 */
export interface PendingReviewRow {
  homework_id: number
  homework_title: string
  student_id: number
  student_name: string
  username: string
  submit_time: string | null
  duration_minutes: number | null
  file_url: string | null
  text_content: string | null
  /** 用时 <1 分钟标记异常 */
  suspicious: boolean
}
```

- [ ] **Step 2: 在 `classes.ts` 加批改接口**

编辑 `zg-tsp-web/src/api/classes.ts`，在 `homeworkApi` 对象的 `remove:` 之后插入：

```typescript
  /** 老师批改作业：打分 + 评语，积分按差额补发/回扣。 */
  review: (homeworkId: number, studentId: number, score: number, comment?: string) =>
    post<{
      record: HomeworkRecordRow
      points_delta: number
      awarded_points: number
    }>('/homework/review', {
      homework_id: homeworkId,
      student_id: studentId,
      score,
      comment: comment ?? null,
    }),

  /** 待批改列表：已提交但未批改的作业。 */
  pending: (page = 1, size = 20) =>
    post<{
      list: PendingReviewRow[]
      total: number
      page: number
      size: number
    }>('/homework/pending', { page, size }),
```

并在该文件的 types import 中补入 `PendingReviewRow`（`HomeworkRecordRow` 若尚未 import 也一并补上）。

- [ ] **Step 3: 在 `parent.ts` 加档位配置接口**

编辑 `zg-tsp-web/src/api/parent.ts`，在文件末尾追加：

```typescript
/** 作业批改档位配置（admin）。沿用本文件混放 admin 接口的现状。 */
export const reviewRuleApi = {
  list: () =>
    post<{ list: HomeworkReviewRule[]; total: number }>('/admin/homework-review-rules/list'),

  create: (minScore: number, points: number) =>
    post<{ rule: HomeworkReviewRule }>('/admin/homework-review-rules/create', {
      min_score: minScore,
      points,
    }),

  update: (id: number, fields: { points?: number; enabled?: boolean }) =>
    post<{ rule: HomeworkReviewRule }>('/admin/homework-review-rules/update', { id, ...fields }),
}
```

并在该文件的 types import 中补入 `HomeworkReviewRule`。

- [ ] **Step 4: 类型检查**

Run:
```bash
cd zg-tsp-web && npx tsc -b --noEmit
```
Expected: 无输出（零错误）

- [ ] **Step 5: 提交**

```bash
git add zg-tsp-web/src/api/types.ts zg-tsp-web/src/api/classes.ts zg-tsp-web/src/api/parent.ts
git commit -m "feat: Web 端补作业批改类型与 API —— 批改、待批改列表、档位配置"
```

---

## Task 7: Web 端批改弹窗组件

**Files:**
- Create: `zg-tsp-web/src/components/ReviewModal.tsx`

**Interfaces:**
- Consumes: `homeworkApi.review`（Task 6）
- Produces: `ReviewModal` 组件，props：
  - `open: boolean`
  - `homeworkId: number`
  - `studentId: number`
  - `studentName: string`
  - `initialScore?: number | null`
  - `initialComment?: string | null`
  - `answerText?: string | null`
  - `answerFileUrl?: string | null`
  - `onClose: () => void`
  - `onDone: () => void`（提交成功后调用，父组件负责刷新）

- [ ] **Step 1: 创建组件**

创建 `zg-tsp-web/src/components/ReviewModal.tsx`：

```tsx
/** 老师批改作业弹窗：打分 + 评语（PRD 5.3）。完成情况页与待批改页共用。 */

import { useEffect, useState } from 'react'
import { App, Button, Descriptions, Input, InputNumber, Modal, Space, Typography } from 'antd'

import { fileUrl } from '../api/client'
import { homeworkApi } from '../api/classes'

interface Props {
  open: boolean
  homeworkId: number
  studentId: number
  studentName: string
  initialScore?: number | null
  initialComment?: string | null
  answerText?: string | null
  answerFileUrl?: string | null
  onClose: () => void
  onDone: () => void
}

export default function ReviewModal({
  open,
  homeworkId,
  studentId,
  studentName,
  initialScore,
  initialComment,
  answerText,
  answerFileUrl,
  onClose,
  onDone,
}: Props) {
  const { message } = App.useApp()
  const [score, setScore] = useState<number>(100)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setScore(initialScore ?? 100)
    setComment(initialComment ?? '')
  }, [open, initialScore, initialComment])

  async function onSubmit() {
    setSaving(true)
    try {
      const r = await homeworkApi.review(homeworkId, studentId, score, comment.trim() || undefined)
      // 用 awarded_points（实际净变动）而非 points_delta（规则差额）：
      // 学生余额不足时实际扣减少于应扣，提示要让老师看到真实数字。
      const a = r.awarded_points
      const shortfall = r.points_delta < 0 && a > r.points_delta
      message.success(
        a > 0
          ? `批改完成，补发 ${a} 积分`
          : a < 0
            ? shortfall
              ? `批改完成，回扣 ${-a} 积分（学生余额不足，未追扣）`
              : `批改完成，回扣 ${-a} 积分`
            : '批改完成',
      )
      onDone()
      onClose()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '批改失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`批改：${studentName}`}
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      confirmLoading={saving}
      okText="提交批改"
      cancelText="取消"
      width={640}
      destroyOnClose
    >
      <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="学生作答">
          <div style={{ whiteSpace: 'pre-wrap' }}>{answerText || '（无文本作答）'}</div>
        </Descriptions.Item>
        {answerFileUrl && (
          <Descriptions.Item label="附件">
            <a href={fileUrl(answerFileUrl)} target="_blank" rel="noreferrer">
              查看上传文件
            </a>
          </Descriptions.Item>
        )}
      </Descriptions>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div>
          <Typography.Text>分数（0–100）</Typography.Text>
          <InputNumber
            min={0}
            max={100}
            value={score}
            onChange={(v) => setScore(v ?? 0)}
            style={{ width: 160, marginLeft: 8 }}
          />
        </div>
        <div>
          <Typography.Text>评语</Typography.Text>
          <Input.TextArea
            rows={4}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="写给学生的评语（选填）"
            style={{ marginTop: 8 }}
          />
        </div>
      </Space>
    </Modal>
  )
}
```

- [ ] **Step 2: 类型检查**

Run:
```bash
cd zg-tsp-web && npx tsc -b --noEmit
```
Expected: 无输出（零错误）

- [ ] **Step 3: 提交**

```bash
git add zg-tsp-web/src/components/ReviewModal.tsx
git commit -m "feat: Web 端新增批改弹窗组件 —— 打分 + 评语，完成情况页与待批改页共用"
```

---

## Task 8: Web 端老师端批改入口与待批改页

**Files:**
- Modify: `zg-tsp-web/src/pages/teacher/HomeworkRecords.tsx`
- Create: `zg-tsp-web/src/pages/teacher/HomeworkPending.tsx`
- Modify: `zg-tsp-web/src/pages/teacher/Homework.tsx`
- Modify: `zg-tsp-web/src/router/index.tsx`

**Interfaces:**
- Consumes: `ReviewModal`（Task 7）、`homeworkApi.pending` / `homeworkApi.review`（Task 6）
- Produces: 路由 `/teacher/homework/pending`

- [ ] **Step 1: 在 `HomeworkRecords.tsx` 加批改列与按钮**

编辑 `zg-tsp-web/src/pages/teacher/HomeworkRecords.tsx`。

在文件顶部的 import 区补入：

```typescript
import ReviewModal from '../../components/ReviewModal'
```

新增状态与弹窗控制：

```typescript
  const [reviewing, setReviewing] = useState<HomeworkRecordRow | null>(null)
```

在 `if (loading) { ... }` 之前（或 return 之前）定义一个分数颜色辅助函数：

```typescript
function scoreColor(v: number): string {
  if (v >= 90) return 'green'
  if (v >= 80) return 'blue'
  if (v >= 60) return 'orange'
  return 'red'
}
```

在 `<Table<HomeworkRecordRow>` 的 `columns` 数组中，在「积分」列之前插入两列：

```typescript
            {
              title: '分数',
              dataIndex: 'review_score',
              width: 90,
              render: (v: number | null) =>
                v == null ? (
                  <span style={{ color: '#999' }}>未批改</span>
                ) : (
                  <Tag color={scoreColor(v)}>{v}</Tag>
                ),
            },
            {
              title: '评语',
              dataIndex: 'review_comment',
              render: (v: string | null) =>
                v ? (
                  <Typography.Text ellipsis={{ tooltip: v }} style={{ maxWidth: 160 }}>
                    {v}
                  </Typography.Text>
                ) : (
                  <span style={{ color: '#999' }}>-</span>
                ),
            },
```

在「操作」列的 render 内（`积分` 列之前，即列定义里 `title: '用时(分)'` 之后）加入批改按钮。为避免破坏现有列结构，把现有「操作」列改为在表格 `columns` 之外用 `render` 追加不便——**改为**：在「用时(分)」列之后插入一个「批改」列：

```typescript
            {
              title: '批改',
              width: 110,
              render: (_: unknown, r) => (
                <Button size="small" onClick={() => setReviewing(r)}>
                  {r.review_score == null ? '批改' : '修改批改'}
                </Button>
              ),
            },
```

在组件 return 的最外层 `<div>` 内、末尾 `</Card>` 之后插入弹窗：

```tsx
      <ReviewModal
        open={reviewing != null}
        homeworkId={homeworkId}
        studentId={reviewing?.student_id ?? 0}
        studentName={reviewing?.nickname || reviewing?.username || ''}
        initialScore={reviewing?.review_score}
        initialComment={reviewing?.review_comment}
        answerText={reviewing?.text_content}
        answerFileUrl={reviewing?.file_url}
        onClose={() => setReviewing(null)}
        onDone={() => void load()}
      />
```

**注意**：`load` 在该组件里是 `useEffect` 里的内联异步函数，不是 `useCallback`——若 `load` 不在组件作用域内定义，需把弹窗的 `onDone` 改为 `() => window.location.reload()` 之外的刷新方式。实现时先确认 `HomeworkRecords.tsx` 中 `load` 的定义位置：它在 `useEffect` 回调内部，因此**不可**在 return 中引用。改为在组件顶层新增一个 state 触发的重载：

```typescript
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    void load()
  }, [load, reloadKey])
```

并把 `onDone` 设为 `() => setReloadKey((k) => k + 1)`。若原文件的 `useEffect` 依赖数组是 `[homeworkId, message]`，改为 `[homeworkId, message, reloadKey]`。

- [ ] **Step 2: 创建待批改页**

创建 `zg-tsp-web/src/pages/teacher/HomeworkPending.tsx`：

```tsx
/** 老师端待批改清单（PRD 5.3）。跨作业汇总已提交但未批改的记录。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Table, Tag } from 'antd'

import ReviewModal from '../../components/ReviewModal'
import { homeworkApi } from '../../api/classes'
import type { PendingReviewRow } from '../../api/types'

export default function TeacherHomeworkPending() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<PendingReviewRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [reviewing, setReviewing] = useState<PendingReviewRow | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await homeworkApi.pending(page, 20)
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, message])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  return (
    <Card title="待批改">
      <Table<PendingReviewRow>
        rowKey={(r) => `${r.homework_id}-${r.student_id}`}
        dataSource={rows}
        loading={loading}
        locale={{ emptyText: '没有待批改的作业' }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        columns={[
          {
            title: '学生',
            dataIndex: 'student_name',
            render: (v: string, r) => (
              <span>
                {v} <span style={{ color: '#999' }}>（{r.username}）</span>
              </span>
            ),
          },
          { title: '作业', dataIndex: 'homework_title' },
          {
            title: '提交时间',
            dataIndex: 'submit_time',
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
          },
          {
            title: '用时(分)',
            dataIndex: 'duration_minutes',
            width: 100,
            render: (v: number | null) => (v == null ? '-' : v),
          },
          {
            title: '异常',
            dataIndex: 'suspicious',
            width: 90,
            render: (v: boolean) => (v ? <Tag color="warning">用时过短</Tag> : '-'),
          },
          {
            title: '操作',
            width: 100,
            render: (_: unknown, r) => (
              <Button size="small" onClick={() => setReviewing(r)}>
                批改
              </Button>
            ),
          },
        ]}
      />

      <ReviewModal
        open={reviewing != null}
        homeworkId={reviewing?.homework_id ?? 0}
        studentId={reviewing?.student_id ?? 0}
        studentName={reviewing?.student_name ?? ''}
        answerText={reviewing?.text_content}
        answerFileUrl={reviewing?.file_url}
        onClose={() => setReviewing(null)}
        onDone={() => setReloadKey((k) => k + 1)}
      />
    </Card>
  )
}
```

- [ ] **Step 3: 在 `Homework.tsx` 加待批改入口**

编辑 `zg-tsp-web/src/pages/teacher/Homework.tsx`。在 import 区补入 `Badge`：

```typescript
import { App, Badge, Button, Card, DatePicker, Form, Input, Popconfirm, Select, Table, Tag } from 'antd'
```

在组件内新增状态与加载逻辑：

```typescript
  const [pendingCount, setPendingCount] = useState(0)

  useEffect(() => {
    ;(async () => {
      try {
        const r = await homeworkApi.pending(1, 1)
        setPendingCount(r.total)
      } catch {
        // 计数失败不阻塞主流程
      }
    })()
  }, [])
```

在「作业列表」Card 的 `extra` 属性里，`Select` 之前插入：

```tsx
          <Badge count={pendingCount} overflowCount={99}>
            <Button onClick={() => navigate('/teacher/homework/pending')}>待批改</Button>
          </Badge>
```

- [ ] **Step 4: 注册路由**

编辑 `zg-tsp-web/src/router/index.tsx`。在 import 区补入：

```typescript
import TeacherHomeworkPending from '../pages/teacher/HomeworkPending'
```

在 teacher 路由块内、`/teacher/homework/:id` 之前插入（顺序要紧，避免 `:id` 抢先匹配 `pending`）：

```tsx
        <Route path="/teacher/homework/pending" element={<TeacherHomeworkPending />} />
```

- [ ] **Step 5: 类型检查与构建**

Run:
```bash
cd zg-tsp-web && npx tsc -b --noEmit
```
Expected: 无输出（零错误）

Run:
```bash
cd zg-tsp-web && npm run build
```
Expected: 构建成功

- [ ] **Step 6: 提交**

```bash
git add zg-tsp-web/src/pages/teacher/HomeworkRecords.tsx zg-tsp-web/src/pages/teacher/HomeworkPending.tsx zg-tsp-web/src/pages/teacher/Homework.tsx zg-tsp-web/src/router/index.tsx
git commit -m "feat: Web 端老师端批改 —— 完成情况页批改列 + 待批改清单页 + 路由"
```

---

## Task 9: Web 端学生端展示与 admin 档位配置

**Files:**
- Modify: `zg-tsp-web/src/pages/student/HomeworkDetail.tsx`
- Modify: `zg-tsp-web/src/pages/admin/Rules.tsx`

**Interfaces:**
- Consumes: `homeworkApi`（Task 6）、`reviewRuleApi`（Task 6）
- Produces: 无新接口

- [ ] **Step 1: 学生端展示批改结果**

编辑 `zg-tsp-web/src/pages/student/HomeworkDetail.tsx`。

在 `{rec?.suspicious && (` 这个 Alert 块之后插入：

```tsx
      {rec?.reviewed_at ? (
        <Card size="small" title="老师批改" style={{ marginBottom: 16 }}>
          <Space align="start" size={24} wrap>
            <Statistic
              title="分数"
              value={rec.review_score ?? 0}
              suffix="分"
              valueStyle={{
                fontSize: 28,
                color:
                  (rec.review_score ?? 0) >= 90
                    ? '#52c41a'
                    : (rec.review_score ?? 0) >= 60
                      ? '#fa8c16'
                      : '#f5222d',
              }}
            />
            <div style={{ flex: 1, minWidth: 240 }}>
              <Typography.Text type="secondary">评语</Typography.Text>
              <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>
                {rec.review_comment || '老师未写评语'}
              </div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                批改时间：{new Date(rec.reviewed_at).toLocaleString()}
              </Typography.Text>
            </div>
          </Space>
        </Card>
      ) : (
        <Alert type="info" showIcon message="老师尚未批改" style={{ marginBottom: 16 }} />
      )}
```

并在 import 中补入 `Statistic`：

```typescript
import { Alert, App, Button, Card, Descriptions, Result, Space, Spin, Statistic, Tag, Upload } from 'antd'
```

**注意**：`rec.reviewed_at` 与 `rec.review_score` 的类型支持由 Task 6 负责 —— `Homework.my_record` 的类型是 `HomeworkRecord | null`，Task 6 已给 `HomeworkRecord` 接口补上 `review_score` / `review_comment` / `reviewed_at` / `review_points` 四个字段。若本步骤编译报「属性不存在」，说明 Task 6 未完成，先回去补。

- [ ] **Step 2: admin 端加档位配置 Card**

编辑 `zg-tsp-web/src/pages/admin/Rules.tsx`。

在 import 区补入：

```typescript
import { reviewRuleApi } from '../../api/parent'
import type { HomeworkReviewRule, PointRule } from '../../api/types'
```

（`PointRule` 若已 import 则不重复加。）

在组件内新增状态：

```typescript
  const [rules, setRules] = useState<HomeworkReviewRule[]>([])
  const [creating, setCreating] = useState(false)
  const [editingRule, setEditingRule] = useState<HomeworkReviewRule | null>(null)
  const [ruleForm] = Form.useForm()
```

在 `load` 函数之后新增档位加载与保存逻辑：

```typescript
  const loadRules = useCallback(async () => {
    try {
      const r = await reviewRuleApi.list()
      setRules(r.list)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载批改档位失败')
    }
  }, [message])

  useEffect(() => {
    void loadRules()
  }, [loadRules])

  async function onCreateRule(values: { min_score: number; points: number }) {
    try {
      await reviewRuleApi.create(values.min_score, values.points)
      message.success('档位已新增')
      setCreating(false)
      ruleForm.resetFields()
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '新增档位失败')
    }
  }

  async function onUpdateRule(values: { points: number; enabled: boolean }) {
    if (!editingRule) return
    try {
      await reviewRuleApi.update(editingRule.id, {
        points: values.points,
        enabled: values.enabled,
      })
      message.success('档位已更新')
      setEditingRule(null)
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '更新档位失败')
    }
  }

  async function onToggleRule(rule: HomeworkReviewRule) {
    try {
      await reviewRuleApi.update(rule.id, { enabled: !rule.enabled })
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }
```

在 return 的最外层，把现有的「积分规则管理」Card 与新增的 Card 包在一个 fragment 里（`<>...</>`），并在现有 Card 之后插入：

```tsx
      <Card
        title="作业批改档位"
        style={{ marginTop: 16 }}
        extra={
          <Button type="primary" onClick={() => setCreating(true)}>
            新增档位
          </Button>
        }
      >
        <Table<HomeworkReviewRule>
          rowKey="id"
          dataSource={rules}
          pagination={false}
          locale={{ emptyText: '暂无档位' }}
          columns={[
            { title: '分数下限（含）', dataIndex: 'min_score', width: 140 },
            {
              title: '积分值',
              dataIndex: 'points',
              width: 100,
              render: (v: number) => <Tag color="gold">{v}</Tag>,
            },
            {
              title: '启用',
              dataIndex: 'enabled',
              width: 100,
              render: (v: boolean, r) => (
                <Switch checked={v} onChange={() => onToggleRule(r)} />
              ),
            },
            {
              title: '操作',
              width: 100,
              render: (_: unknown, r) => (
                <Button
                  size="small"
                  onClick={() => {
                    setEditingRule(r)
                    ruleForm.setFieldsValue({ points: r.points, enabled: r.enabled })
                  }}
                >
                  编辑
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增档位"
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={() => ruleForm.submit()}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <Form form={ruleForm} layout="vertical" onFinish={onCreateRule}>
          <Form.Item
            name="min_score"
            label="分数下限（含）"
            rules={[{ required: true, message: '请输入分数下限' }]}
            extra="该分数及以上命中此档；下限不可重复"
          >
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="points"
            label="积分值"
            rules={[{ required: true, message: '请输入积分值' }]}
          >
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingRule ? `编辑档位：${editingRule.min_score} 分及以上` : ''}
        open={editingRule != null}
        onCancel={() => setEditingRule(null)}
        onOk={() => ruleForm.submit()}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <Form form={ruleForm} layout="vertical" onFinish={onUpdateRule}>
          <Form.Item name="points" label="积分值" rules={[{ required: true, message: '请输入积分值' }]}>
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
```

**注意**：新增与编辑两个 Modal 共用同一个 `ruleForm`，打开编辑时 `setFieldsValue` 会覆盖新增表单的残留值。实现时在 `setCreating(true)` 前调用 `ruleForm.resetFields()`，在 `setEditingRule(r)` 前也调用 `ruleForm.resetFields()` 再 `setFieldsValue`。

- [ ] **Step 3: 类型检查与构建**

Run:
```bash
cd zg-tsp-web && npx tsc -b --noEmit && npm run build
```
Expected: 构建成功，无类型错误

- [ ] **Step 4: 提交**

```bash
git add zg-tsp-web/src/pages/student/HomeworkDetail.tsx zg-tsp-web/src/pages/admin/Rules.tsx
git commit -m "feat: Web 端学生端展示批改结果 + admin 端作业批改档位配置"
```

---

## Task 10: 移动端老师端批改

**Files:**
- Modify: `zg-tsp-android/lib/core/apis.dart`
- Modify: `zg-tsp-android/lib/pages/teacher/teacher_home.dart`
- Modify: `zg-tsp-ios/lib/core/apis.dart`
- Modify: `zg-tsp-ios/lib/pages/teacher/teacher_home.dart`

**Interfaces:**
- Consumes: `POST /homework/review`
- Produces:
  - `TeacherApi.instance.reviewHomework(int homeworkId, int studentId, int score, String comment) -> Future<Json>`
  - `_HomeworkRecordsPage` 每条记录可点「批改」打开底部弹层

- [ ] **Step 1: 在 android 端 `apis.dart` 加接口**

编辑 `zg-tsp-android/lib/core/apis.dart`，在 `TeacherApi` 类中（`homeworkRecords` 方法之后）插入：

```dart
  /// 老师批改作业：打分 + 评语，积分按差额补发/回扣（PRD 5.3）。
  Future<Json> reviewHomework(int homeworkId, int studentId, int score, String comment) =>
      ApiClient.instance.post('/homework/review', body: {
        'homework_id': homeworkId,
        'student_id': studentId,
        'score': score,
        'comment': comment,
      });
```

- [ ] **Step 2: 在 android 端 `teacher_home.dart` 加批改弹层**

编辑 `zg-tsp-android/lib/pages/teacher/teacher_home.dart`。

在 `_HomeworkRecordsPageState` 类中新增 state 字段：

```dart
  bool _reviewing = false;
```

在 `_HomeworkRecordsPageState` 的 `build` 方法中，把记录卡片改成带「批改」按钮。找到记录卡片的 `ListTile`（当前只有 `title`/`subtitle`/`trailing`），在 `trailing` 之前加入批改入口，并在 ListTile 上加 `onTap` 打开弹层。

实现方式：在 `_HomeworkRecordsPageState` 里加一个方法：

```dart
  Future<void> _openReview(
    int homeworkId,
    Map<String, dynamic> r,
  ) async {
    final scoreCtrl = TextEditingController(
      text: (r['review_score'] as num?)?.toInt().toString() ?? '100',
    );
    final commentCtrl =
        TextEditingController(text: r['review_comment'] as String? ?? '');

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 16,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('批改：${r['nickname'] ?? r['username'] ?? ''}',
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text('学生作答：${r['text_content'] ?? '（无）'}'),
            const SizedBox(height: 12),
            TextField(
              controller: scoreCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '分数（0-100）'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: commentCtrl,
              maxLines: 3,
              decoration: const InputDecoration(labelText: '评语（选填）'),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () async {
                final score = int.tryParse(scoreCtrl.text.trim()) ?? -1;
                if (score < 0 || score > 100) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('分数需在 0-100 之间')),
                  );
                  return;
                }
                final messenger = ScaffoldMessenger.of(ctx);
                try {
                  await TeacherApi.instance.reviewHomework(
                    homeworkId,
                    r['student_id'] as int,
                    score,
                    commentCtrl.text.trim(),
                  );
                  if (!mounted) return;
                  messenger
                    ..hideCurrentSnackBar()
                    ..showSnackBar(const SnackBar(content: Text('批改完成')));
                  Navigator.pop(ctx);
                  _load();
                } catch (e) {
                  messenger
                    ..hideCurrentSnackBar()
                    ..showSnackBar(SnackBar(content: Text(errorMessage(e))));
                }
              },
              child: const Text('提交批改'),
            ),
          ],
        ),
      ),
    );

    scoreCtrl.dispose();
    commentCtrl.dispose();
  }
```

在记录卡片的 `ListTile` 上加 `onTap`，并加一个「批改」按钮：

```dart
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          TextButton(
                            onPressed: () => _openReview(
                              widget.homeworkId,
                              r,
                            ),
                            child: Text(
                              (r['review_score'] as num?) == null
                                  ? '批改'
                                  : '修改批改',
                            ),
                          ),
                          Chip(
```

**注意**：`r` 是 `rows[i] as Map<String, dynamic>`，在 `_HomeworkRecordsPageState.build` 的 `itemBuilder` 里已有该变量名，直接复用。

- [ ] **Step 3: 同步到 ios 端**

把 android 端改过的两个文件（`lib/core/apis.dart`、`lib/pages/teacher/teacher_home.dart`）**逐字节复制**到 ios 端对应位置：

```bash
cp zg-tsp-android/lib/core/apis.dart zg-tsp-ios/lib/core/apis.dart
cp zg-tsp-android/lib/pages/teacher/teacher_home.dart zg-tsp-ios/lib/pages/teacher/teacher_home.dart
```

**注意**：CLAUDE.md 说明两端 `lib/` 几乎逐字节相同，差异只在包名与注释。本次改动不涉及包名相关代码，**直接覆盖是安全的**——但覆盖后必须 `git diff` 确认 ios 端没有产生非预期的大范围差异：

```bash
cd zg-tsp-ios && git diff --stat
```
Expected: 只有 `lib/core/apis.dart` 与 `lib/pages/teacher/teacher_home.dart` 两个文件被改动，且改动量与 android 端一致

- [ ] **Step 4: 静态分析**

Run:
```bash
cd zg-tsp-android && flutter analyze
```
Expected: `No issues found!`

Run:
```bash
cd zg-tsp-ios && flutter analyze
```
Expected: `No issues found!`

**注意**：若报 `avoid_print` 或 `use_build_context_synchronously` 类警告，说明 `context` 在 async gap 后被使用——按上面代码的写法，`ctx` 是 `showModalBottomSheet` 的 builder 参数，在其内部使用是安全的；`mounted` 检查已覆盖 `context` 的跨 gap 使用。

- [ ] **Step 5: 提交**

```bash
git add zg-tsp-android/lib zg-tsp-ios/lib
git commit -m "feat: 移动端老师端作业批改 —— 分数 + 评语弹层（android/ios 同步）"
```

---

## Task 11: 移动端学生端展示批改结果

**Files:**
- Modify: `zg-tsp-android/lib/pages/student/homework_page.dart`
- Modify: `zg-tsp-ios/lib/pages/student/homework_page.dart`

**Interfaces:**
- Consumes: `StudentApi.instance.homeworkDetail` 返回的 `my_record`（已含批改字段，服务端 Task 4 提供）
- Produces: 移动端学生作业详情页显示分数与评语

- [ ] **Step 1: 在 android 端展示批改结果**

编辑 `zg-tsp-android/lib/pages/student/homework_page.dart`。

在 `HomeworkDetailPage` 的 `build` 方法中，找到展示提交信息的区块（当前显示 `用时`、`状态`、`积分`），在其后插入批改结果区块：

```dart
              if (rec?['reviewed_at'] != null) ...[
                const SizedBox(height: 12),
                Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('老师批改',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        Text(
                          '分数：${rec?['review_score'] ?? '-'} 分',
                          style: const TextStyle(fontSize: 16),
                        ),
                        const SizedBox(height: 4),
                        Text('评语：${rec?['review_comment'] ?? '老师未写评语'}'),
                      ],
                    ),
                  ),
                ),
              ] else ...[
                const SizedBox(height: 12),
                const Text('老师尚未批改'),
              ],
```

**注意**：`rec` 是从 `d['homework']?['my_record']` 取出的，可能为 null。上面的写法用 `rec?['...']` 做了空安全处理。若该文件中 `rec` 的类型是 `Map<String, dynamic>?`，则 `rec?['review_score']` 合法。

- [ ] **Step 2: 同步到 ios 端**

```bash
cp zg-tsp-android/lib/pages/student/homework_page.dart zg-tsp-ios/lib/pages/student/homework_page.dart
```

Run:
```bash
cd zg-tsp-ios && git diff --stat
```
Expected: 只有 `lib/pages/student/homework_page.dart` 被改动

- [ ] **Step 3: 静态分析**

Run:
```bash
cd zg-tsp-android && flutter analyze && cd ../zg-tsp-ios && flutter analyze
```
Expected: 两端均 `No issues found!`

- [ ] **Step 4: 提交**

```bash
git add zg-tsp-android/lib zg-tsp-ios/lib
git commit -m "feat: 移动端学生端展示老师批改结果（android/ios 同步）"
```

---

## Task 12: 文档同步（PRD / init.sql / 验收脚本）

**Files:**
- Modify: `zg-tsp-docs/sys_doc/PRD.md`
- Regenerate: `zg-tsp-docs/sql/init.sql`
- Modify: `zg-tsp-docs/scripts/acceptance_check.py`

**Interfaces:**
- Consumes: Task 1–11 的实现
- Produces: 与实现一致的契约文档

- [ ] **Step 1: 重新生成 init.sql**

Run:
```bash
cd zg-tsp-server && python -m app.seed.export_ddl
```
Expected: 输出生成路径 `zg-tsp-docs/sql/init.sql`

Run:
```bash
grep -n "homework_review_rules\|review_score\|review_points" zg-tsp-docs/sql/init.sql
```
Expected: 能查到新表与新字段

- [ ] **Step 2: PRD 5.3 补批改小节**

编辑 `zg-tsp-docs/sys_doc/PRD.md`，在 `### 5.3 老师端 — 作业管理` 小节的条目列表末尾（`- 删除作业（仅无人提交时）` 之后）追加：

```markdown
- 批改作业：打分（0–100）+ 评语，学生端可见
- 分数换算积分：按「作业批改档位」表（分数下限 → 积分）换算，admin 可配
- 改分按差额补发/回扣；学生余额不足时扣到 0 为止，不追扣
- 待批改清单：跨作业汇总已提交但未批改的记录
```

- [ ] **Step 3: PRD 4.1 补建表 SQL**

编辑 `zg-tsp-docs/sys_doc/PRD.md`，在 `### 4.1 建表 SQL` 章节的 `homework_records` 建表语句之后追加：

```sql
-- 作业批改档位
CREATE TABLE homework_review_rules
(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    min_score  INTEGER UNIQUE NOT NULL,
    points     INTEGER        NOT NULL DEFAULT 0,
    enabled    BOOLEAN DEFAULT 1,
    updated_by INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 作业记录表补批改字段
-- ALTER TABLE homework_records ADD COLUMN review_score    INTEGER;
-- ALTER TABLE homework_records ADD COLUMN review_comment  TEXT;
-- ALTER TABLE homework_records ADD COLUMN reviewed_at     DATETIME;
-- ALTER TABLE homework_records ADD COLUMN reviewed_by     INTEGER;
-- ALTER TABLE homework_records ADD COLUMN review_points   INTEGER NOT NULL DEFAULT 0;
```

- [ ] **Step 4: PRD 第 7 节补接口清单**

编辑 `zg-tsp-docs/sys_doc/PRD.md`，在 `POST /articles/records` 那一组之前（作业接口组内）追加：

```
POST /homework/review           {homework_id, student_id, score, comment}  teacher
POST /homework/pending          {page, size}                             teacher
```

并在 admin 接口组内追加：

```
POST /admin/homework-review-rules/list                                   admin
POST /admin/homework-review-rules/update   {id, points?, enabled?}        admin
POST /admin/homework-review-rules/create   {min_score, points}           admin
```

- [ ] **Step 5: PRD 4.2 补档位种子说明**

编辑 `zg-tsp-docs/sys_doc/PRD.md`，在 `### 4.2 积分规则种子数据` 小节的表格之后追加：

```markdown
**作业批改档位种子**（表 `homework_review_rules`，与 `point_rules` 分工不同）：

| min_score | points | 说明 |
|-----------|--------|------|
| 90 | 5 | 优秀 |
| 80 | 3 | 良好 |
| 60 | 1 | 合格 |

匹配规则：取所有 `enabled` 且 `min_score <= score` 的档位中 `min_score` 最大的一档；
无匹配则发 0 积分（不报错）。批改积分记 `point_logs.type='review'`，
与提交时自动发放的 `homework` 类型隔离。
```

- [ ] **Step 6: 验收脚本补断言**

编辑 `zg-tsp-docs/scripts/acceptance_check.py`。先读该文件了解现有断言的组织方式，再按同样风格补一组：

```python
def check_homework_review(base_url, token):
    """作业批改验收（PRD 5.3）：批改 + 分数换算积分 + 学生端可见。"""
    # 待批改列表可访问
    r = post(base_url, "/homework/pending", {"page": 1, "size": 20}, token)
    assert r["code"] == 0, "待批改列表失败"
    assert "list" in r["data"], "待批改列表缺 list 字段"

    # 档位配置接口 admin 可访问
    r = post(base_url, "/admin/homework-review-rules/list", {}, admin_token)
    assert r["code"] == 0, "档位配置列表失败"
```

实际实现时按该文件已有的 helper 名称与断言风格改写，不要引入新的 helper。

- [ ] **Step 7: 跑验收脚本**

Run:
```bash
python zg-tsp-docs/scripts/acceptance_check.py
```
Expected: 全部断言通过

- [ ] **Step 8: 提交**

```bash
git add zg-tsp-docs/sql/init.sql zg-tsp-docs/sys_doc/PRD.md zg-tsp-docs/scripts/acceptance_check.py
git commit -m "docs: 同步 PRD 批改小节、init.sql 重新生成、验收脚本补断言"
```

---

## Task 13: 同步到独立仓库并端到端验证

**Files:**
- Sync: 全部改动同步到 `/Users/zg/PycharmProjects/zg-tsp-repos/`

**Interfaces:**
- Consumes: Task 1–12 的全部改动
- Produces: 独立仓库与快照一致，服务实际运行新代码

- [ ] **Step 1: 生成同步补丁**

```bash
cd /Users/zg/PycharmProjects/zg-tsp && git diff --cached > /tmp/zgtsp-homework-review.patch
```

**注意**：本任务的实施过程中可能有多次提交，`git diff --cached` 只含暂存内容。改用：

```bash
cd /Users/zg/PycharmProjects/zg-tsp && git diff dfd80bc..HEAD -- zg-tsp-server zg-tsp-web zg-tsp-android zg-tsp-ios zg-tsp-docs > /tmp/zgtsp-homework-review.patch
```

（`dfd80bc` 是本次功能开发前的基线 commit；若基线不同，用 `git log --oneline` 找到开发前的那个 commit。）

- [ ] **Step 2: 应用到独立仓库**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos && git apply --check /tmp/zgtsp-homework-review.patch && git apply /tmp/zgtsp-homework-review.patch
```
Expected: 无输出（应用成功）

**注意**：`zg-tsp-repos/` 根目录不是 git 仓库，五个子目录各自是独立仓库。`git apply` 在根目录执行时按文件路径操作，与仓库边界无关。

- [ ] **Step 3: 校验两边一致**

```bash
for f in zg-tsp-server/app/models/entities.py zg-tsp-server/app/db/repo.py zg-tsp-server/app/routers/homework.py zg-tsp-server/app/routers/homework_review_admin.py zg-tsp-server/app/services/point_service.py zg-tsp-web/src/pages/teacher/HomeworkRecords.tsx zg-tsp-web/src/pages/teacher/HomeworkPending.tsx zg-tsp-android/lib/pages/teacher/teacher_home.dart zg-tsp-ios/lib/pages/teacher/teacher_home.dart; do
  diff -q "/Users/zg/PycharmProjects/zg-tsp-repos/$f" "/Users/zg/PycharmProjects/zg-tsp/$f" >/dev/null && echo "一致 $f" || echo "不一致 $f"
done
```
Expected: 全部「一致」

- [ ] **Step 4: 重启服务端并验证接口**

服务端是 `--reload` 模式，应已自动重载。若未重载，重启：

```bash
# 找到进程并重启
lsof -Pan -p $(pgrep -f "uvicorn app.main:app" | head -1) -iTCP -sTCP:LISTEN
```

Run:
```bash
# 凭据从环境变量取，不写进仓库
: "${TEACHER_USERNAME:?请先 export TEACHER_USERNAME=<老师账号>}"
: "${TEACHER_PASSWORD:?请先 export TEACHER_PASSWORD=<密码>}"
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TEACHER_USERNAME\",\"password\":\"$TEACHER_PASSWORD\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")
curl -s -X POST http://127.0.0.1:8000/homework/pending -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" -d '{"page":1,"size":20}' | python -m json.tool
```
Expected: `{"code": 0, ...}`，`data.list` 含待批改记录（若库里有未批改的提交）

- [ ] **Step 5: 端到端批改验证**

用上面拿到的 token 与一个真实的 `homework_id` + `student_id`：

```bash
curl -s -X POST http://127.0.0.1:8000/homework/review -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" -d '{"homework_id": 1, "student_id": 3, "score": 88, "comment": "端到端验证"}' | python -m json.tool
```
Expected: `"code": 0`，`data.record.review_score == 88`，`data.awarded_points` 为对应档位积分

- [ ] **Step 6: Web 端构建验证**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-web && npx tsc -b --noEmit && npm run build
```
Expected: 构建成功

- [ ] **Step 7: 跑全部服务端测试**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-server && python -m pytest -q
```
Expected: 全部 PASS

- [ ] **Step 8: 移动端静态分析**

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-android && flutter analyze
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-ios && flutter analyze
```
Expected: 两端均 `No issues found!`

- [ ] **Step 9: 提交（独立仓库各自提交）**

五个独立仓库分别提交：

```bash
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-server && git add -A && git commit -m "feat: 作业批改功能 —— 数据模型、批改接口、待批改列表、档位配置"
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-web && git add -A && git commit -m "feat: 作业批改功能 —— 老师端批改、待批改页、学生端展示、admin 档位配置"
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-android && git add -A && git commit -m "feat: 作业批改功能 —— 老师端批改弹层、学生端展示"
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-ios && git add -A && git commit -m "feat: 作业批改功能 —— 老师端批改弹层、学生端展示"
cd /Users/zg/PycharmProjects/zg-tsp-repos/zg-tsp-docs && git add -A && git commit -m "docs: 同步作业批改功能的 PRD、init.sql、验收脚本"
```

---

## 验收清单

全部任务完成后，逐项确认：

- [ ] `python -m pytest -q` 全部通过（服务端）
- [ ] `npm run build` 成功（Web 端）
- [ ] `flutter analyze` 两端 `No issues found!`
- [ ] `python zg-tsp-docs/scripts/acceptance_check.py` 全部通过
- [ ] 老师端：进入作业完成情况页 → 点「批改」→ 填分数与评语 → 提交 → 表格显示分数与评语
- [ ] 老师端：点「待批改」→ 看到待批改清单 → 批改后该条从清单消失
- [ ] 老师端：改分 → 积分按差额补发/回扣
- [ ] 学生端：作业详情页看到「老师批改」区块（分数 + 评语 + 时间）
- [ ] admin 端：积分规则页下方「作业批改档位」可增改启停；新增档位后新批改按新档位换算
- [ ] 独立仓库与快照文件一致（`diff -q` 全部「一致」）
