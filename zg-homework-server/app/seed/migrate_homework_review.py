"""作业批改功能数据迁移：新增批改字段 + 建档位表 + 写档位种子。

仓库**无 Alembic**，`Base.metadata.create_all()` 只建缺失的表、
**不修改已有表的结构**，因此新增列必须显式 ALTER。

已存在的非空档位表保持原样；空表状态无法区分中断与管理员有意清空，须人工处理。

**注意：DDL 不是原子的。** MySQL 的 DDL 会隐式提交，`engine.begin()` 的事务
边界保护不了 DDL。首次建表后种子提交前中断，重跑会检测到空表并停止，
不会猜测或覆盖管理员配置；请参考报错及 PRD 人工恢复。

用法：
    python -m app.seed.migrate_homework_review
    python -m app.seed.migrate_homework_review --check   # 只检查不修改
"""

import argparse

from sqlalchemy import text

from app.db.session import engine

# 档位种子复用 initial_data 的定义，避免三处（迁移脚本 / initial_data / init.sql）漂移
from app.seed.initial_data import DEFAULT_REVIEW_RULES  # noqa: E402  (避免循环导入放最后)

# (列名, MySQL 列定义)
NEW_COLUMNS = [
    ("review_score", "INTEGER NULL COMMENT '批改分数 0–100；NULL 表示未批改'"),
    ("review_comment", "TEXT NULL COMMENT '老师评语'"),
    ("reviewed_at", "DATETIME NULL COMMENT '批改时间'"),
    ("reviewed_by", "INTEGER NULL COMMENT '批改老师用户ID'"),
    ("review_points", "INTEGER NOT NULL DEFAULT 0 COMMENT '批改积分实际净变动累计'"),
    ("review_target_points", "INTEGER NULL COMMENT '上次批改目标档位积分；未批改为NULL'"),
]

# (索引名, 列列表) —— 与 ORM `HomeworkRecord.__table_args__` 保持一致
NEW_INDEXES = [
    ("ix_homework_records_pending", "homework_id, reviewed_at"),
    ("ix_homework_records_reviewed_by", "reviewed_by"),
]

# (min_score, points) 种子档位 —— 与 initial_data.DEFAULT_REVIEW_RULES 同源
SEED_RULES = DEFAULT_REVIEW_RULES

CREATE_TABLE_SQL = """
CREATE TABLE homework_review_rules (
    id          INTEGER      NOT NULL AUTO_INCREMENT COMMENT '档位ID',
    min_score   INTEGER      NOT NULL COMMENT '档位分数下限（含）',
    points      INTEGER      NOT NULL DEFAULT 0 COMMENT '该档位发放的积分',
    enabled     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用；false 则跳过该档',
    updated_by  INTEGER      NULL COMMENT '最后修改人（admin）ID',
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最后修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_homework_review_rules_min_score (min_score),
    KEY ix_homework_review_rules_updated_by (updated_by)
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


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ),
        {"t": table},
    ).scalar()
    return bool(row)


def _existing_indexes(conn) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'homework_records'"
        )
    )
    return {row[0] for row in rows}


def _existing_min_scores(conn) -> set[int]:
    rows = conn.execute(text("SELECT min_score FROM homework_review_rules"))
    return {row[0] for row in rows}


def _backfill_review_targets(conn, check_only: bool) -> int:
    """按当前档位初始化旧记录；仅填 NULL，不覆盖已保存的目标。"""
    count = conn.execute(text(
        "SELECT COUNT(*) FROM homework_records "
        "WHERE review_score IS NOT NULL AND review_target_points IS NULL"
    )).scalar_one()
    if count and not check_only:
        conn.execute(text(
            "UPDATE homework_records SET review_target_points = COALESCE("
            "(SELECT points FROM homework_review_rules "
            "WHERE enabled = 1 AND min_score <= homework_records.review_score "
            "ORDER BY min_score DESC LIMIT 1), 0) "
            "WHERE review_score IS NOT NULL AND review_target_points IS NULL"
        ))
    print(f"{'待初始化' if check_only else '已初始化'}批改目标：{count} 条")
    return count


def main(check_only: bool = False) -> None:
    with engine.begin() as conn:
        # 前置校验：homework_records 不存在时 ALTER 会抛原始驱动错误，
        # 信息量太低，这里提前给出可操作的提示。
        if not _table_exists(conn, "homework_records"):
            raise RuntimeError("表 homework_records 不存在，请先建表")

        # 必须在任何 DDL 或回填前检查，避免空表被误当作零积分规则。
        table_exists = _table_exists(conn, "homework_review_rules")
        if table_exists and not _existing_min_scores(conn):
            raise RuntimeError(
                "homework_review_rules 已存在但为空：可能是首次建表后中断，"
                "也可能是管理员有意清空，无法自动判断。请停止迁移，人工核对"
                "备份及管理员意图，恢复或明确配置所需档位后再重跑；"
                "不要直接补默认档位或删除表。详见 PRD。"
            )

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

        # 索引：create_all 不会给已有表补索引，需显式 CREATE
        have_indexes = _existing_indexes(conn)
        for index_name, index_cols in NEW_INDEXES:
            if index_name in have_indexes:
                print(f"跳过（已存在）：索引 {index_name}")
                continue
            if check_only:
                print(f"待新增：索引 {index_name} ({index_cols})")
                continue
            conn.execute(
                text(f"CREATE INDEX {index_name} ON homework_records ({index_cols})")
            )
            print(f"已新增：索引 {index_name} ({index_cols})")

        # 不使用 IF NOT EXISTS：并发建表时必须失败，不能误种入别人的表。
        if table_exists:
            print("跳过（已存在）：表 homework_review_rules")
        elif check_only:
            print("待建表：homework_review_rules")
        else:
            conn.execute(text(CREATE_TABLE_SQL))

        # 仅首次建表时写默认档位；已有表可能被管理员有意清空或调整，
        # 迁移必须保留现有配置，回填也应基于迁移前的规则。
        have = _existing_min_scores(conn) if table_exists else set()
        seed_rules = [] if table_exists else SEED_RULES
        for min_score, points in seed_rules:
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

        # --check 时新列尚不存在，按已批改记录数报告待初始化数量。
        if check_only and ("review_target_points" in added or "review_score" in added):
            if "review_score" in existing:
                count = conn.execute(text(
                    "SELECT COUNT(*) FROM homework_records WHERE review_score IS NOT NULL"
                )).scalar_one()
                print(f"待初始化批改目标：{count} 条（使用迁移时的档位）")
            else:
                print("待初始化批改目标：0 条")
        else:
            _backfill_review_targets(conn, check_only)

    if added:
        verb = "待新增列" if check_only else "已新增列"
        print(f"{verb}：{', '.join(added)}")
    elif not check_only:
        print("无需变更")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="作业批改功能数据迁移")
    parser.add_argument("--check", action="store_true", help="只检查待更新项，不修改")
    args = parser.parse_args()
    main(check_only=args.check)
