"""从 ORM 导出 MySQL 8 建表 SQL，生成 `zg-tsp-docs/sql/init.sql`。

**为什么要有这个脚本**

服务端原本只有 `python -m app.seed.initial_data`，走 SQLAlchemy `create_all()`
建表 —— 部署到一台空机器时，运维没法用一条 `mysql < init.sql` 完成初始化。
本脚本把建表 SQL 从 ORM 编译出来，作为可交付、可审计的脚本落盘。

**为什么必须从 ORM 生成，而不是抄 PRD**

`zg-tsp-docs/sys_doc/PRD.md` 4.1 节的建表 SQL 是 **SQLite 方言**
（`INTEGER PRIMARY KEY AUTOINCREMENT`、`BOOLEAN`），与服务端实际跑的 MySQL 8
不符。库表结构的唯一权威是 `app/models/entities.py`（CLAUDE.md 明确）。
手抄 PRD 立刻就会引入方言问题，故此处一律从元数据编译。

**两处必须做的翻译（否则生成的 SQL 在 MySQL 上跑不通）**

1. `default=` 是 **Python 层默认值**，SQLAlchemy 编译时不产出 DB 层 DEFAULT。
   不翻译的话会有 52 个列变成「NOT NULL 且无默认值」，纯 SQL 插入 admin
   会因 `total_points` / `status` / `must_change_password` 缺值而失败。
2. `func.now()` 编译出的是 `DEFAULT now()`，**MySQL 8.0.13 之前是语法错误**
   （8.0.13 起才支持函数默认值表达式）。统一改写为 `DEFAULT CURRENT_TIMESTAMP`。
**用法**

    python -m app.seed.export_ddl              # 生成到 ../zg-tsp-docs/sql/init.sql
    python -m app.seed.export_ddl --stdout     # 打到标准输出，不落盘
    python -m app.seed.export_ddl --out /path/to/init.sql

改了 `app/models/entities.py` 后要重新跑一次，让 `init.sql` 与 ORM 保持同步。
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import Column, Index
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.models.entities import Base

# 目标库字符集，与现有开发库（zg_tsp）保持一致
CHARSET = "utf8mb4"
COLLATION = "utf8mb4_0900_ai_ci"

# admin 密码哈希占位符：由 scripts/init.sh 在运行时替换成实际 bcrypt 哈希。
# SQL 文件本身不含任何可登录的密码。
ADMIN_HASH_PLACEHOLDER = "__ADMIN_BCRYPT_HASH__"

# 种子积分规则与作业批改档位复用 initial_data 的定义，避免两处漂移
from app.seed.initial_data import (  # noqa: E402  (避免循环导入放最后)
    DEFAULT_POINT_RULES,
    DEFAULT_REVIEW_RULES,
)

_DIALECT = mysql.dialect()


def _sql_literal(value) -> str | None:
    """把 Python 值转成 SQL 字面量。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _column_default(column: Column) -> tuple[str | None, str | None]:
    """取列的 DB 层 DEFAULT。

    返回 `(编译输出中已存在的 DEFAULT 文本, 期望写入的 DEFAULT 文本)`。

    - 已存在的文本为 None 表示编译输出里没有 DEFAULT 子句（Python 层
      `default=` 就是这种情况），此时把期望值插进去。
    - `func.now()` 一律改写为 `CURRENT_TIMESTAMP`：`DEFAULT now()` 在
      **MySQL 8.0.13 之前是语法错误**（8.0.13 起才支持函数默认值表达式）。
    """
    if column.server_default is not None:
        arg = column.server_default.arg
        if hasattr(arg, "compile"):
            existing = str(arg.compile(dialect=_DIALECT))
            desired = (
                "CURRENT_TIMESTAMP"
                if existing.lower() in ("now()", "current_timestamp()")
                else existing
            )
            return existing, desired
        literal = _sql_literal(arg)
        return literal, literal

    if column.default is not None:
        arg = column.default.arg
        if callable(arg):
            # 可调用的默认值视为时间函数
            return None, "CURRENT_TIMESTAMP"
        literal = _sql_literal(arg)
        return None, literal

    return None, None


def _index_clause(index: Index) -> str:
    """把 Index 对象渲染成内联的 KEY / UNIQUE KEY 子句。"""
    cols = ", ".join(expr.name for expr in index.expressions)
    unique = "UNIQUE " if index.unique else ""
    return f"{unique}KEY `{index.name}` ({cols})"


def _render_table(table) -> str:
    """渲染单张表的 CREATE TABLE 语句。

    做法：编译 SQLAlchemy 的 CREATE TABLE，然后**按块**重组而不是做字符串
    修补 —— 之前用正则剥离外键会留下悬空逗号导致语法错误，按块拼接则始终
    自洽（每个块自己不带尾逗号，拼接时统一加）。
    """
    compiled = str(CreateTable(table).compile(dialect=_DIALECT)).strip()
    lines = [ln.rstrip() for ln in compiled.split("\n")]

    column_names = {c.name for c in table.columns}

    # 拆成块：首行 `CREATE TABLE xxx (` 是表头，末行 `)COMMENT='...'` 是收尾，
    # 其余为表体
    body: list[str] = []
    tail = ""
    for idx, ln in enumerate(lines):
        stripped = ln.strip()
        if idx == 0:
            continue  # 表头由本函数自己拼
        if stripped.startswith(")"):
            tail = stripped
            continue
        # 去掉行尾逗号，拼接时统一处理
        body.append(stripped.rstrip(","))

    # 注入 DB 层 DEFAULT + 内联 KEY
    rendered: list[str] = []
    for block in body:
        first_token = block.split()[0].strip("`") if block else ""
        if first_token in column_names:
            # 列定义行：把 DEFAULT 改写成期望值，或在缺失时插入
            column = next(c for c in table.columns if c.name == first_token)
            existing, desired = _column_default(column)
            if desired and existing and f"DEFAULT {existing}" in block:
                block = block.replace(f"DEFAULT {existing}", f"DEFAULT {desired}", 1)
            elif desired and " DEFAULT " not in block:
                block = block.replace(" COMMENT ", f" DEFAULT {desired} COMMENT ", 1)
        rendered.append(block)

    # 内联索引（SQLAlchemy 默认把 Index 单独编译成 CREATE INDEX 语句）
    index_clauses = [
        _index_clause(ix) for ix in sorted(table.indexes, key=lambda i: i.name or "")
    ]
    if index_clauses:
        rendered.extend(index_clauses)

    parts = ",\n\t".join(rendered)
    return f"CREATE TABLE IF NOT EXISTS `{table.name}` (\n\t{parts}\n{tail}"


def _render_point_rule_seeds() -> list[str]:
    """积分规则种子（PRD 4.2），幂等写入。"""
    statements = []
    for key, name, points, daily_limit, extra in DEFAULT_POINT_RULES:
        limit_sql = "NULL" if daily_limit is None else str(daily_limit)
        extra_sql = (
            "'" + json.dumps(extra, ensure_ascii=False).replace("'", "''") + "'"
            if extra
            else "NULL"
        )
        statements.append(
            "INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)\n"
            f"SELECT '{key}', '{name}', {points}, {limit_sql}, {extra_sql}, 1\n"
            "FROM DUAL\n"
            f"WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = '{key}');"
        )
    return statements


def _render_review_rule_seeds() -> list[str]:
    """作业批改档位种子（PRD 5.3），幂等写入。

    部署路径是 `scripts/init.sh` 导入本文件，它**不跑**任何 `migrate_*` 脚本。
    档位表为空时批改会**静默发 0 积分**（匹配规则是「无匹配则发 0，不报错」），
    故这三行种子必须内嵌在 init.sql 里。
    """
    statements = []
    for min_score, points in DEFAULT_REVIEW_RULES:
        statements.append(
            "INSERT INTO homework_review_rules (min_score, points, enabled)\n"
            f"SELECT {min_score}, {points}, 1\n"
            "FROM DUAL\n"
            f"WHERE NOT EXISTS (SELECT 1 FROM homework_review_rules WHERE min_score = {min_score});"
        )
    return statements


def _render_admin_seed() -> str:
    """admin 账户种子，幂等写入。

    已存在 admin 时**不覆盖**其密码 —— 避免重跑初始化把运维已改过的密码打回
    原形。首登强制改密由 `must_change_password=1` 保证（PRD 5.1）。
    """
    return (
        "INSERT INTO users (username, password_hash, role, nickname, total_points, status, must_change_password)\n"
        f"SELECT 'admin', '{ADMIN_HASH_PLACEHOLDER}', 'admin', '超级管理员', 0, 'active', 1\n"
        "FROM DUAL\n"
        "WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');"
    )


def build_sql() -> str:
    """生成完整的 init.sql 文本。"""
    if any(table.foreign_keys for table in Base.metadata.tables.values()):
        raise ValueError("ORM 元数据包含物理外键，禁止导出")
    out: list[str] = []
    out.append("-- ============================================================================")
    out.append("-- zg-tsp 数据库初始化脚本")
    out.append("--")
    out.append("-- 本文件由 `python -m app.seed.export_ddl` **自动生成**，请勿手工编辑。")
    out.append(
        "-- 权威来源：`zg-tsp-server/app/models/entities.py`"
        f"（{len(Base.metadata.tables)} 张表）。"
    )
    out.append("-- 改了 ORM 后重新执行该脚本以保持同步。")
    out.append("--")
    out.append("-- 用法（推荐经 scripts/init.sh，它会替换 admin 密码占位符）：")
    out.append("--     mysql --default-character-set=utf8mb4 <库名> < init.sql")
    out.append("--")
    out.append("-- 说明：")
    out.append("--   · 全部语句幂等，可重复执行")
    out.append("--   · 不创建物理外键，关联完整性由应用维护")
    out.append(f"--   · admin 密码以占位符 {ADMIN_HASH_PLACEHOLDER} 写入，")
    out.append("--     直接用 mysql 导入会导致 admin 无法登录，必须经 scripts/init.sh")
    out.append("-- ============================================================================")
    out.append("")
    out.append("SET NAMES utf8mb4;")
    out.append("")

    for table in Base.metadata.sorted_tables:
        out.append(f"-- --- {table.name} ---")
        out.append(_render_table(table) + ";")
        out.append("")

    out.append("-- --- 积分规则种子（PRD 4.2）---")
    out.extend(_render_point_rule_seeds())
    out.append("")

    out.append("-- --- 作业批改档位种子（PRD 5.3）---")
    out.extend(_render_review_rule_seeds())
    out.append("")

    out.append("-- --- admin 账户 ---")
    out.append(_render_admin_seed())
    out.append("")

    return "\n".join(out)


def default_output_path() -> Path:
    """默认输出路径：仓库根下的 zg-tsp-docs/sql/init.sql。

    独立仓库布局下 zg-tsp-server 与 zg-tsp-docs 同级，本推导同样成立。
    """
    server_root = Path(__file__).resolve().parents[2]
    return server_root.parent / "zg-tsp-docs" / "sql" / "init.sql"


def main() -> None:
    parser = argparse.ArgumentParser(description="从 ORM 导出 MySQL 建表 SQL")
    parser.add_argument("--out", help="输出文件路径（默认 ../zg-tsp-docs/sql/init.sql）")
    parser.add_argument("--stdout", action="store_true", help="打到标准输出，不写文件")
    args = parser.parse_args()

    sql = build_sql()

    if args.stdout:
        sys.stdout.write(sql)
        return

    out_path = Path(args.out) if args.out else default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8")
    print(f"已生成：{out_path}")
    print(f"表数量：{len(Base.metadata.tables)}")


if __name__ == "__main__":
    main()
