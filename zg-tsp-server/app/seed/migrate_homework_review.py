"""作业批改功能数据迁移：新增批改字段 + 建档位表 + 写档位种子。

仓库**无 Alembic**，`Base.metadata.create_all()` 只建缺失的表、
**不修改已有表的结构**，因此新增列必须显式 ALTER。

本脚本**幂等**：已存在的列/表/索引/种子直接跳过，可重复执行。

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
    ("review_points", "INTEGER NOT NULL DEFAULT 0 COMMENT '实际已发放的批改积分（改分时按差额补发/回扣）'"),
]

# (约束名, 列名, 被引用表) —— 与 ORM `reviewed_by` 的 ForeignKey("users.id") 对齐
NEW_FOREIGN_KEYS = [
    ("fk_homework_records_reviewed_by", "reviewed_by", "users"),
]

# (索引名, 列列表) —— 与 ORM `HomeworkRecord.__table_args__` 保持一致
NEW_INDEXES = [
    ("ix_homework_records_pending", "homework_id, reviewed_at"),
]

# (min_score, points) 种子档位
SEED_RULES = [(90, 5), (80, 3), (60, 1)]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS homework_review_rules (
    id          INTEGER      NOT NULL AUTO_INCREMENT,
    min_score   INTEGER      NOT NULL,
    points      INTEGER      NOT NULL DEFAULT 0,
    enabled     TINYINT(1)   NOT NULL DEFAULT 1,
    updated_by  INTEGER      NULL,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
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


def _existing_foreign_keys(conn) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT DISTINCT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'homework_records'"
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

        # 外键：ORM 里 reviewed_by 指向 users.id，create_all 不会给已有表补外键
        have_fks = _existing_foreign_keys(conn)
        for fk_name, fk_col, fk_ref in NEW_FOREIGN_KEYS:
            if fk_name in have_fks:
                print(f"跳过（已存在）：外键 {fk_name}")
                continue
            if check_only:
                print(f"待新增：外键 {fk_name} ({fk_col} → {fk_ref}.id)")
                continue
            conn.execute(
                text(
                    f"ALTER TABLE homework_records ADD CONSTRAINT {fk_name} "
                    f"FOREIGN KEY ({fk_col}) REFERENCES {fk_ref} (id)"
                )
            )
            print(f"已新增：外键 {fk_name} ({fk_col} → {fk_ref}.id)")

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

        # 档位表（IF NOT EXISTS，幂等）
        table_exists = _table_exists(conn, "homework_review_rules")
        if check_only:
            if table_exists:
                print("跳过（已存在）：表 homework_review_rules")
            else:
                print("待建表：homework_review_rules")
        else:
            conn.execute(text(CREATE_TABLE_SQL))

        # 档位种子
        have = _existing_min_scores(conn) if table_exists else set()
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
        verb = "待新增列" if check_only else "已新增列"
        print(f"{verb}：{', '.join(added)}")
    elif not check_only:
        print("无需变更")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="作业批改功能数据迁移")
    parser.add_argument("--check", action="store_true", help="只检查待更新项，不修改")
    args = parser.parse_args()
    main(check_only=args.check)
