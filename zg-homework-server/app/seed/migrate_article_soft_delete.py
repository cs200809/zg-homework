"""Add article soft-delete column to an existing MySQL schema.

Run once before deploying the new application: python -m app.seed.migrate_article_soft_delete
MySQL DDL implicitly commits; serialize migration invocations operationally.
"""
from sqlalchemy import text


def migrate(conn):
    exists = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'articles' "
        "AND COLUMN_NAME = 'deleted_at'"
    )).scalar()
    if not exists:
        conn.execute(text("ALTER TABLE articles ADD COLUMN deleted_at DATETIME NULL COMMENT '软删除时间'"))


def main():
    from app.db.session import engine
    with engine.begin() as conn:
        migrate(conn)


if __name__ == '__main__':
    main()
