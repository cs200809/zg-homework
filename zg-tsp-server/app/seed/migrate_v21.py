"""迭代 v2.1 数据迁移：为 `articles` 表增加 file_url / file_name / file_type。

仓库**无 Alembic**，`Base.metadata.create_all()` 只建缺失的表、
**不修改已有表的结构**，因此新增列必须显式 ALTER。

本脚本**幂等**：已存在的列直接跳过，可重复执行。

用法：
    python -m app.seed.migrate_v21
"""

from sqlalchemy import text

from app.db.session import engine

# (列名, MySQL 列定义)
NEW_COLUMNS = [
    ("file_url", "VARCHAR(255) NULL COMMENT '原始上传文件路径（迭代 v2.1）'"),
    ("file_name", "VARCHAR(255) NULL COMMENT '原始文件名（迭代 v2.1）'"),
    ("file_type", "VARCHAR(20) NULL COMMENT '原始文件类型：pdf / docx（迭代 v2.1）'"),
]


def _existing_columns(conn) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'articles'"
        )
    )
    return {row[0] for row in rows}


def main() -> None:
    with engine.begin() as conn:
        existing = _existing_columns(conn)
        added: list[str] = []
        for name, ddl in NEW_COLUMNS:
            if name in existing:
                print(f"跳过（已存在）：{name}")
                continue
            conn.execute(text(f"ALTER TABLE articles ADD COLUMN {name} {ddl}"))
            added.append(name)
    if added:
        print(f"已新增列：{', '.join(added)}")
    else:
        print("无需变更")


if __name__ == "__main__":
    main()
