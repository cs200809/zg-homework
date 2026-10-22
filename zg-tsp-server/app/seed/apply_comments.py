"""为已存在的表补齐字段与表级 COMMENT。

`Base.metadata.create_all()` 只在表不存在时建表，**不会修改已有表结构**，
因此新增 comment 后必须显式执行本脚本。

用法：
    python -m app.seed.apply_comments          # 补齐/更新注释
    python -m app.seed.apply_comments --check  # 只检查，不修改
"""

import argparse
import logging

from sqlalchemy import inspect, text

from app.db.session import engine
from app.models.entities import Base

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _quote(identifier: str) -> str:
    return f"`{identifier}`"


def _render_default(default) -> str:
    """把 information_schema.COLUMN_DEFAULT 还原成合法 SQL。

    MySQL 8 对时间戳类默认值返回字面量 'now()'，需转回 CURRENT_TIMESTAMP；
    字符串默认值在 information_schema 中已去掉引号，需补回。
    """
    s = str(default)
    if s.upper() in ("NOW()", "CURRENT_TIMESTAMP"):
        return "CURRENT_TIMESTAMP"
    # 纯数字（含小数、负号）不加引号
    if s.replace(".", "", 1).replace("-", "", 1).isdigit():
        return s
    return f"'{s}'"


def apply(check_only: bool = False) -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    changed_tables = 0
    changed_columns = 0

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                logger.warning("表 %s 不存在，跳过（请先运行建表）", table.name)
                continue

            # --- 表级 COMMENT ---
            if table.comment:
                current = conn.execute(
                    text(
                        "SELECT TABLE_COMMENT FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                    ),
                    {"t": table.name},
                ).scalar()
                if current != table.comment:
                    logger.info("[表] %s：%r → %r", table.name, current, table.comment)
                    changed_tables += 1
                    if not check_only:
                        conn.execute(
                            text(
                                f"ALTER TABLE {_quote(table.name)} "
                                f"COMMENT = :c"
                            ),
                            {"c": table.comment},
                        )

            # --- 字段级 COMMENT ---
            # 关键：MODIFY COLUMN 会重写整个列定义，必须显式带上
            # NOT NULL / DEFAULT / AUTO_INCREMENT，否则会把这些属性丢掉。
            current = {
                row[0]: row
                for row in conn.execute(
                    text(
                        "SELECT COLUMN_NAME, COLUMN_COMMENT, IS_NULLABLE, COLUMN_DEFAULT, "
                        "       EXTRA, COLUMN_TYPE "
                        "FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                    ),
                    {"t": table.name},
                )
            }
            for col in table.columns:
                if not col.comment:
                    continue
                info = current.get(col.name)
                if info and info[1] == col.comment:
                    continue

                logger.info("[字段] %s.%s：%r → %r",
                            table.name, col.name, info[1] if info else None, col.comment)
                changed_columns += 1
                if check_only or info is None:
                    continue

                _, _, nullable, default, extra, col_type = info
                parts = [
                    f"ALTER TABLE {_quote(table.name)}",
                    f"MODIFY COLUMN {_quote(col.name)} {col_type}",
                ]
                if nullable == "NO":
                    parts.append("NOT NULL")
                if default is not None:
                    parts.append(f"DEFAULT {_render_default(default)}")
                if extra and "auto_increment" in extra.lower():
                    parts.append("AUTO_INCREMENT")
                parts.append("COMMENT :c")

                conn.execute(text(" ".join(parts)), {"c": col.comment})

    if check_only:
        logger.info("检查完成：%d 个表、%d 个字段待更新", changed_tables, changed_columns)
    else:
        logger.info("注释已更新：%d 个表、%d 个字段", changed_tables, changed_columns)


def main() -> None:
    parser = argparse.ArgumentParser(description="补齐数据库字段注释")
    parser.add_argument("--check", action="store_true", help="只检查待更新项，不修改")
    args = parser.parse_args()
    apply(check_only=args.check)


if __name__ == "__main__":
    main()