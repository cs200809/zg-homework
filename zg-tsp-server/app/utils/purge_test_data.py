"""清除开发库中的测试数据（开发/运维用）。

背景：pytest 直接跑在开发库 zg_tsp 上，测试数据会不断累积
（历史遗留曾把库撑到近 7000 个用户），也让「哪些是真实数据」难以分辨。

现在测试数据统一以 **test_ 前缀**标识（用户名为 test_xxx，
班级邀请码以 T 开头、老师邀请码以 TEST 开头），因此清理有两种模式：

**按前缀**（默认，快）：删掉所有 test_ 开头的用户及其关联数据。
新产生的测试数据都能被清掉，不必维护清单。

**按清单**（--by-keep-list）：只保留下列种子数据，其余全删。
用于清理历史遗留的旧命名测试数据（t{hex}_、ac_、dbg_ 等）。

保留清单：
- 5 个种子账号：admin / teacher01 / student01 / student02 / parent01
- 种子班级「三年二班」（邀请码 CLS2024）与邀请码 TEACH2024
- 家长绑定关系（parent01 ↔ student01）
- 10 条积分规则、成语题库种子题

用法：
    python -m app.utils.purge_test_data --dry-run     # 只统计不删除
    python -m app.utils.purge_test_data               # 交互确认后执行
    python -m app.utils.purge_test_data --by-keep-list  # 按保留清单清理

⚠️ 危险操作：不可撤销，请先备份数据库。
"""

import argparse
import sys

from sqlalchemy import text

from app.db.session import SessionLocal, engine

# --- 保留清单 ---

# 种子账号（联调与验收用，PRD 12 节）
KEEP_USERNAMES = ("admin", "teacher01", "student01", "student02", "parent01")

# 种子班级名与邀请码
KEEP_CLASS_NAMES = ("三年二班",)
KEEP_CLASS_INVITE_CODES = ("CLS2024",)
KEEP_INVITE_CODES = ("TEACH2024",)

# 家长绑定：parent01 ↔ student01
KEEP_PARENT_BINDINGS = (("parent01", "student01"),)

# 需要先清空的「子表」（含 users 外键）。顺序按外键依赖自底向上。
# 表名 -> 是否保留种子行（True 表示按业务键保留）
CHILD_TABLES = (
    # 直接引用 users 的表
    "reading_records",
    "game_records",
    "checkins",
    "point_logs",
    "homework_records",
    "parent_students",
    "articles",
    "admin_logs",
    "idiom_questions",
    "teacher_invite_codes",
    "homework",
    "users",
)


def _kept_user_ids(db, by_keep_list: bool) -> list[int]:
    """确定要保留的用户 id 集合。

    by_keep_list=True  → 只保留种子账号（用于清理历史旧命名残留）
    by_keep_list=False → 只删 test_ 前缀的账号，其余（种子 + 手工建的）全留
    """
    if by_keep_list:
        rows = db.execute(
            text("SELECT id FROM users WHERE username IN :names").bindparams(
                names=tuple(KEEP_USERNAMES)
            )
        ).all()
        return [r[0] for r in rows]

    rows = db.execute(text("SELECT id FROM users WHERE username NOT LIKE 'test\\_%'")).all()
    return [r[0] for r in rows]


def _kept_class_ids(db, by_keep_list: bool) -> list[int]:
    """确定要保留的班级 id 集合。

    by_keep_list=True 时按种子班级精确锁定 —— 不能只按班级名匹配，
    测试里也建过同名班级（teacher_id 指向测试老师），保留它们会导致
    删 users 时外键报错。

    by_keep_list=False 时保留所有非测试班级（班主任不是 test_ 账号的班）。
    """
    if by_keep_list:
        rows = db.execute(
            text(
                "SELECT id FROM classes "
                "WHERE invite_code IN :codes OR (name IN :names AND teacher_id = 1)"
            ).bindparams(
                codes=tuple(KEEP_CLASS_INVITE_CODES),
                names=tuple(KEEP_CLASS_NAMES),
            )
        ).all()
        return [r[0] for r in rows]

    rows = db.execute(
        text(
            "SELECT c.id FROM classes c "
            "LEFT JOIN users u ON u.id = c.teacher_id "
            "WHERE u.id IS NULL OR u.username NOT LIKE 'test\\_%'"
        )
    ).all()
    return [r[0] for r in rows]


def _kept_invite_ids(db, by_keep_list: bool, kept_users: list[int]) -> list[int]:
    """确定要保留的老师邀请码 id 集合。"""
    if by_keep_list:
        rows = db.execute(
            text("SELECT id FROM teacher_invite_codes WHERE code IN :codes").bindparams(
                codes=tuple(KEEP_INVITE_CODES)
            )
        ).all()
        return [r[0] for r in rows]

    # 老师邀请码：以下任一情形即删除
    #   - 创建者是测试账号（测试创建的码一律不留）
    #   - 使用者是非保留用户（否则删 users 时外键报错）
    # 不能只看 code 前缀 —— 服务端 /admin/invite/create 生成的码是随机 12 位，
    # 没有固定前缀，只能靠关联的用户判定。
    # 保留 = 创建者与使用者都在保留集合内（使用者可为空）。
    # 反过来，只要有一端指向将被删除的用户，这个邀请码就必须一起删，
    # 否则删 users 时外键约束会报错。
    rows = db.execute(
        text(
            "SELECT i.id FROM teacher_invite_codes i "
            "LEFT JOIN users cu ON cu.id = i.created_by "
            "LEFT JOIN users uu ON uu.id = i.used_by_user_id "
            "WHERE cu.id IN :ids "
            "  AND (uu.id IS NULL OR uu.id IN :ids) "
            "  AND i.code NOT LIKE 'TEST%'"
        ),
        {"ids": tuple(kept_users) or (0,)},
    ).all()
    return [r[0] for r in rows]


def _plan(db, by_keep_list: bool) -> dict:
    """统计各表将被删除的行数。"""
    kept_users = _kept_user_ids(db, by_keep_list)
    kept_classes = _kept_class_ids(db, by_keep_list)

    plan: dict[str, int] = {}

    for table in CHILD_TABLES:
        if table == "users":
            n = db.execute(
                text(
                    "SELECT COUNT(*) FROM users WHERE id NOT IN :ids"
                ).bindparams(ids=tuple(kept_users) or (0,))
            ).scalar_one()
            plan[table] = n
            continue

        if table == "homework":
            # 作业属于保留的班级则保留
            n = db.execute(
                text(
                    "SELECT COUNT(*) FROM homework WHERE class_id NOT IN :ids"
                ).bindparams(ids=tuple(kept_classes) or (0,))
            ).scalar_one()
            plan[table] = n
            continue

        if table == "teacher_invite_codes":
            kept_invites = _kept_invite_ids(db, by_keep_list, kept_users)
            n = db.execute(
                text(
                    "SELECT COUNT(*) FROM teacher_invite_codes WHERE id NOT IN :ids"
                ).bindparams(ids=tuple(kept_invites) or (0,))
            ).scalar_one()
            plan[table] = n
            continue

        if table == "parent_students":
            # 家长或学生有一方是测试账号即删除
            n = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM parent_students ps
                    LEFT JOIN users pu ON pu.id = ps.parent_id
                    LEFT JOIN users su ON su.id = ps.student_id
                    WHERE pu.id IS NULL OR pu.id NOT IN :ids
                       OR su.id IS NULL OR su.id NOT IN :ids
                    """
                ),
                {"ids": tuple(kept_users) or (0,)},
            ).scalar_one()
            plan[table] = n
            continue

        if table == "idiom_questions":
            # 成语题库：保留由**非测试账号**创建的题（种子题 + admin 手工导入）
            n = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM idiom_questions iq
                    LEFT JOIN users u ON u.id = iq.created_by
                    WHERE u.id IS NULL OR u.username LIKE 'test\\_%'
                    """
                )
            ).scalar_one()
            plan[table] = n
            continue

        if table == "admin_logs":
            # 操作者是测试账号的审计日志即删除
            n = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM admin_logs al
                    LEFT JOIN users u ON u.id = al.admin_id
                    WHERE u.id IS NULL OR u.id NOT IN :ids
                    """
                ),
                {"ids": tuple(kept_users) or (0,)},
            ).scalar_one()
            plan[table] = n
            continue

        if table == "homework_records":
            # 与 _purge 保持同一条件：学生非保留，或所属作业的班级非保留
            n = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM homework_records hr
                    LEFT JOIN homework hw ON hw.id = hr.homework_id
                    LEFT JOIN users u ON u.id = hr.student_id
                    WHERE u.id IS NULL OR u.id NOT IN :ids
                       OR hw.id IS NULL OR hw.class_id NOT IN :cids
                    """
                ),
                {"ids": tuple(kept_users) or (0,), "cids": tuple(kept_classes) or (0,)},
            ).scalar_one()
            plan[table] = n
            continue

        # 其余表：只要引用了非保留用户就删
        n = db.execute(
            text(
                f"SELECT COUNT(*) FROM {table} t "
                f"WHERE EXISTS (SELECT 1 FROM users u WHERE u.id = t.{_user_col(table)} "
                "AND u.id NOT IN :ids)"
            ).bindparams(ids=tuple(kept_users) or (0,))
        ).scalar_one()
        plan[table] = n

    # reading_records 通过 articles 间接引用用户，需要单独按文章清
    plan["reading_records"] = db.execute(
        text(
            """
            SELECT COUNT(*) FROM reading_records rr
            LEFT JOIN articles a ON a.id = rr.article_id
            WHERE a.id IS NULL
               OR a.author_id NOT IN :ids
            """
        ).bindparams(ids=tuple(kept_users) or (0,))
    ).scalar_one()

    return plan


def _user_col(table: str) -> str:
    return {
        "reading_records": "student_id",
        "game_records": "student_id",
        "checkins": "student_id",
        "point_logs": "student_id",
        "homework_records": "student_id",
        "parent_students": "parent_id",
        "articles": "author_id",
        "admin_logs": "admin_id",
        "idiom_questions": "created_by",
        "teacher_invite_codes": "created_by",
        "homework": "teacher_id",
    }[table]


def _purge(db, by_keep_list: bool) -> dict:
    """执行清理，返回各表实际删除行数。"""
    kept_users = _kept_user_ids(db, by_keep_list)
    kept_classes = _kept_class_ids(db, by_keep_list)
    kept_invites = _kept_invite_ids(db, by_keep_list, kept_users)
    deleted: dict[str, int] = {}

    def run(sql: str, **params) -> int:
        result = db.execute(text(sql), params)
        return result.rowcount

    # 先删间接依赖：reading_records -> articles
    deleted["reading_records"] = run(
        """
        DELETE rr FROM reading_records rr
        LEFT JOIN articles a ON a.id = rr.article_id
        WHERE a.id IS NULL OR a.author_id NOT IN :ids
        """,
        ids=tuple(kept_users) or (0,),
    )

    for table in (
        "game_records",
        "checkins",
        "point_logs",
        "articles",
    ):
        deleted[table] = run(
            f"DELETE FROM {table} WHERE {_user_col(table)} NOT IN :ids",
            ids=tuple(kept_users) or (0,),
        )

    # 作业提交记录：既按学生过滤，也按所属作业的班级过滤 ——
    # 后面要删非保留班级的作业，其提交记录必须先删，否则外键报错。
    deleted["homework_records"] = run(
        """
        DELETE hr FROM homework_records hr
        LEFT JOIN homework hw ON hw.id = hr.homework_id
        LEFT JOIN users u ON u.id = hr.student_id
        WHERE u.id IS NULL OR u.id NOT IN :ids
           OR hw.id IS NULL OR hw.class_id NOT IN :cids
        """,
        ids=tuple(kept_users) or (0,),
        cids=tuple(kept_classes) or (0,),
    )

    # parent_students：家长或学生有一方是测试账号即删除
    deleted["parent_students"] = run(
        """
        DELETE ps FROM parent_students ps
        LEFT JOIN users pu ON pu.id = ps.parent_id
        LEFT JOIN users su ON su.id = ps.student_id
        WHERE pu.id IS NULL OR pu.id NOT IN :ids
           OR su.id IS NULL OR su.id NOT IN :ids
        """,
        ids=tuple(kept_users) or (0,),
    )

    # 审计日志：操作者是测试账号的即删除
    deleted["admin_logs"] = run(
        """
        DELETE al FROM admin_logs al
        LEFT JOIN users u ON u.id = al.admin_id
        WHERE u.id IS NULL OR u.id NOT IN :ids
        """,
        ids=tuple(kept_users) or (0,),
    )

    # 成语题库：删掉由测试账号创建的题。
    # MySQL 不允许 DELETE 的子查询引用同一张表，改用 LEFT JOIN 判存在性。
    deleted["idiom_questions"] = run(
        """
        DELETE iq FROM idiom_questions iq
        LEFT JOIN users u ON u.id = iq.created_by
        WHERE u.id IS NULL OR u.username LIKE 'test\\_%'
        """
    )

    # 邀请码：只删保留清单之外的
    deleted["teacher_invite_codes"] = run(
        "DELETE FROM teacher_invite_codes WHERE id NOT IN :ids",
        ids=tuple(kept_invites) or (0,),
    )

    # 作业：保留班级下的作业
    deleted["homework"] = run(
        "DELETE FROM homework WHERE class_id NOT IN :ids",
        ids=tuple(kept_classes) or (0,),
    )

    # 班级：保留种子班级（先解绑学生的 class_id）
    deleted["users_class"] = run(
        "UPDATE users SET class_id = NULL WHERE class_id NOT IN :ids",
        ids=tuple(kept_classes) or (0,),
    )
    deleted["classes"] = run(
        "DELETE FROM classes WHERE id NOT IN :ids",
        ids=tuple(kept_classes) or (0,),
    )

    # 积分规则的 updated_by 指向 users，删用户前先把指向非保留用户的置空，
    # 否则外键约束会阻止删除。指向 admin 的保留（审计语义更准确）。
    run(
        "UPDATE point_rules SET updated_by = NULL "
        "WHERE updated_by IS NOT NULL AND updated_by NOT IN :ids",
        ids=tuple(kept_users) or (0,),
    )

    # 用户：删非保留账号
    deleted["users"] = run(
        "DELETE FROM users WHERE id NOT IN :ids",
        ids=tuple(kept_users) or (0,),
    )

    db.commit()
    return deleted


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.utils.purge_test_data",
        description="清除开发库中的测试数据（保留种子数据）",
    )
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    parser.add_argument("--dry-run", action="store_true", help="只统计不删除")
    parser.add_argument(
        "--by-keep-list",
        action="store_true",
        help="按保留清单清理（只留种子数据）；"
        "默认只删 test_ 前缀的测试数据",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        plan = _plan(db, args.by_keep_list)
        print("计划清理：")
        total = 0
        for table, n in plan.items():
            print(f"  {table:24} {n:6} 行")
            total += n
        print(f"  {'合计':24} {total:6} 行")

        if args.dry_run:
            print("\n--dry-run，未做任何改动。")
            return 0

        if not args.yes:
            print("\n⚠️  此操作不可撤销。建议先备份数据库。")
            answer = input("确认删除？(输入 yes 继续) ").strip().lower()
            if answer != "yes":
                print("已取消。")
                return 1

        deleted = _purge(db, args.by_keep_list)
        print("\n实际删除：")
        for table, n in deleted.items():
            print(f"  {table:24} {n:6} 行")
    finally:
        db.close()

    print("\n✓ 清理完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
