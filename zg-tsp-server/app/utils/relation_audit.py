"""只读关系清单与孤儿统计；不从应用配置获取数据库地址。

用法：设置只读账号的连接串环境变量后执行
    python -m app.utils.relation_audit --database-url-env AUDIT_DATABASE_URL
也可使用 --inventory 离线查看清单。建议在一致性快照或业务静默期间运行。
仅发出 SELECT；账号应在数据库端授予只读权限。报告不包含行值或异常详情。
未配置经验证的 TLS，连接仅允许 127.0.0.1 或 ::1，不接受 URL 查询参数。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
import sys

from sqlalchemy import LargeBinary, String, cast, column, create_engine, func, select, table, type_coerce
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Relation:
    source_table: str
    source_column: str
    target_table: str
    nullable: bool
    roles: tuple[str, ...] = ()
    target_column: str = 'id'
    kind: str = 'foreign_key'
    discriminator: str | None = None
    # 迁移后需要保留或创建的以引用列为首列的索引，而非声称当前物理索引存在。
    index_columns: tuple[str, ...] = ()
    # 附加的等值过滤（列名, 值），用于同一条引用在不同业务类型下角色不同的情况。
    extra_where: tuple[tuple[str, str], ...] = ()
    # 该项只做角色检查，不重复统计孤儿（存在性由覆盖全量的关系负责）。
    role_only: bool = False


def _r(source, field, target, nullable=False, roles=(), *, kind='foreign_key',
       discriminator=None, extra_where=(), role_only=False):
    return Relation(source, field, target, nullable, roles, 'id', kind, discriminator,
                    (field,), tuple(extra_where), role_only)


def _byte_exact(col, dialect_name='mysql'):
    """大小写敏感的比较表达式。

    MySQL 默认 utf8mb4_0900_ai_ci 排序规则下 `role IN ('student')` 会匹配
    'STUDENT'，而应用按 Python 精确比较角色，这样的值对应用无效却不会被计入异常。

    按方言选择等价写法：
    - MySQL：`CAST(col AS BINARY)`。不用 `COLLATE binary` —— 在 utf8mb4 列上
      会报 illegal mix of collations。
    - SQLite：`collate('BINARY')`。SQLite 原生支持，且不改变列的排序规则。
      这里不能用 `CAST(... AS BLOB)`：SQLite 的 BLOB 与字符串参数比较会报
      TypeError。
    """
    if dialect_name == 'sqlite':
        return col.collate('BINARY')
    # 比较参数保持字符串类型，避免 LargeBinary 的绑定处理器要求 bytes。
    return type_coerce(cast(col, LargeBinary), String())


# 兼容旧名
_exact = _byte_exact


# 独立于 ORM 元数据构造；迁移后删除物理外键仍可审计。
RELATIONS = (
    _r('users', 'class_id', 'classes', True),
    _r('classes', 'teacher_id', 'users', roles=('teacher',)),
    _r('teacher_invite_codes', 'created_by', 'users', roles=('admin',)),
    _r('teacher_invite_codes', 'used_by_user_id', 'users', True, ('teacher',)),
    _r('homework', 'class_id', 'classes'),
    _r('homework', 'teacher_id', 'users', roles=('teacher',)),
    _r('homework_records', 'homework_id', 'homework'),
    _r('homework_records', 'student_id', 'users', roles=('student',)),
    _r('homework_records', 'reviewed_by', 'users', True, ('teacher',)),
    _r('homework_review_rules', 'updated_by', 'users', True, ('admin',)),
    _r('checkins', 'student_id', 'users', roles=('student',)),
    _r('articles', 'author_id', 'users', roles=('teacher', 'admin')),
    _r('reading_records', 'article_id', 'articles'),
    _r('reading_records', 'student_id', 'users', roles=('student',)),
    _r('game_records', 'student_id', 'users', roles=('student',)),
    _r('point_logs', 'student_id', 'users', roles=('student',)),
    # 操作人：先按全量统计存在性（覆盖所有流水类型），再按类型核对角色。
    # 各类型的操作人语义（见各 router 的 operator_id=）：
    #   checkin / homework / reading / game → 学生本人
    #   review（批改）→ 老师；consume（家长扣分）→ 家长
    # type 是普通列而非多态分派列，故用 extra_where 而非 discriminator。
    _r('point_logs', 'operator_id', 'users', True),
    _r('point_logs', 'operator_id', 'users', True, ('student',),
       extra_where=(('type', 'checkin'),), role_only=True),
    _r('point_logs', 'operator_id', 'users', True, ('student',),
       extra_where=(('type', 'homework'),), role_only=True),
    _r('point_logs', 'operator_id', 'users', True, ('student',),
       extra_where=(('type', 'reading'),), role_only=True),
    _r('point_logs', 'operator_id', 'users', True, ('student',),
       extra_where=(('type', 'game'),), role_only=True),
    _r('point_logs', 'operator_id', 'users', True, ('teacher',),
       extra_where=(('type', 'review'),), role_only=True),
    _r('point_logs', 'operator_id', 'users', True, ('parent',),
       extra_where=(('type', 'consume'),), role_only=True),
    _r('parent_students', 'parent_id', 'users', roles=('parent',)),
    _r('parent_students', 'student_id', 'users', roles=('student',)),
    _r('point_rules', 'updated_by', 'users', True, ('admin',)),
    _r('admin_logs', 'admin_id', 'users', roles=('admin',)),
    _r('idiom_questions', 'created_by', 'users', True, ('admin',)),
    *(_r('admin_logs', 'target_id', target, True, kind='historical', discriminator=name)
      for name, target in (
          ('user', 'users'), ('point_rule', 'point_rules'),
          ('teacher_invite_code', 'teacher_invite_codes'), ('article', 'articles'),
          ('homework_review_rule', 'homework_review_rules'), ('idiom_question', 'idiom_questions'),
      )),
)


def _counts(connection, relation):
    dialect = connection.dialect.name
    # 源表列：引用列、target_type（多态分派）、以及 extra_where 用到的列。
    source_columns = [column(relation.source_column), column('target_type', String)]
    for column_name, _ in relation.extra_where:
        if column_name not in ('target_type', relation.source_column):
            source_columns.append(column(column_name))
    source = table(relation.source_table, *source_columns)
    target = table(relation.target_table, column(relation.target_column), column('role', String))
    ref = source.c[relation.source_column]
    target_id = target.c[relation.target_column]
    scope = []
    if relation.discriminator is not None:
        scope.append(_byte_exact(source.c.target_type, dialect) == relation.discriminator)
    for column_name, value in relation.extra_where:
        scope.append(_byte_exact(source.c[column_name], dialect) == value)
    def count(query):
        return int(connection.execute(query).scalar_one())
    base = select(func.count()).select_from(source)
    missing = ~select(1).select_from(target).where(target_id == ref).exists()
    result = {}
    if not relation.role_only:
        result['orphans'] = count(base.where(*scope, ref.is_not(None), missing))
        if relation.kind == 'historical':
            result['historical_missing'] = result.pop('orphans')
        if not relation.nullable:
            result['unexpected_nulls'] = count(base.where(*scope, ref.is_(None)))
    if relation.roles:
        query = select(func.count()).select_from(source.join(target, ref == target_id))
        # 角色比较必须大小写敏感（见 _exact 的说明）。
        role_col = _byte_exact(target.c.role, dialect)
        result['role_mismatches'] = count(
            query.where(
                *scope,
                (target.c.role.is_(None)) | (role_col.notin_(relation.roles)),
            )
        )
    return result


def _unknown_discriminator_counts(connection):
    """统计 admin_logs 中 target_type 未登记在清单内的历史引用。

    多态引用按 target_type 分派到不同目标表；未登记的类型既不属于任何
    已知关系，也无法判断其目标是否存在，若静默跳过则无法发现未识别的
    关系元数据，故单独计数。

    需要覆盖两种「未知」：
    - target_type 为 NULL（NOT IN 对 NULL 求值为 UNKNOWN，不会命中）
    - target_type 大小写与清单不符（如 'USER'）—— 在不区分大小写的
      排序规则下会匹配到已知分支，故同样要计入未知
    """
    known = tuple(
        r.discriminator for r in RELATIONS if r.discriminator is not None
    )
    source = table('admin_logs', column('target_id'), column('target_type', String))
    ref = source.c.target_id
    type_col = _byte_exact(source.c.target_type, connection.dialect.name)
    # 未知 = target_type 为 NULL，或精确比较后不属于已知清单。
    # NULL 必须单独判定：`NOT IN` 遇 NULL 求值为 UNKNOWN，不会命中该行。
    unknown_type = source.c.target_type.is_(None)
    if known:
        unknown_type = unknown_type | (~type_col.in_(known))
    else:
        unknown_type = unknown_type | source.c.target_type.is_not(None)
    unknown_scope = [ref.is_not(None), unknown_type]
    return {
        'unknown_target_types': int(
            connection.execute(
                select(func.count()).select_from(source).where(*unknown_scope)
            ).scalar_one()
        )
    }


def _unknown_point_log_types(connection):
    """统计 point_logs 中未登记在清单内的流水类型。

    流水类型未登记时，无法判断该行的操作人角色语义（学生本人 / 老师 /
    家长），故单独计数，避免这类行被静默漏掉。
    """
    known = tuple(
        value
        for relation in RELATIONS
        for column_name, value in relation.extra_where
        if column_name == 'type'
    )
    source = table('point_logs', column('operator_id'), column('type', String))
    scope = [source.c.operator_id.is_not(None)]
    type_col = _byte_exact(source.c.type, connection.dialect.name)
    if known:
        scope.append(source.c.type.is_(None) | (~type_col.in_(known)))
    return {
        'unknown_point_log_types': int(
            connection.execute(
                select(func.count()).select_from(source).where(*scope)
            ).scalar_one()
        )
    }


def audit_relations(connection, relations=RELATIONS):
    results = []
    for relation in relations:
        item = asdict(relation)
        try:
            item.update(_counts(connection, relation))
        except Exception:
            # 不输出驱动异常：可能包含 URL、参数或业务数据。
            item['error'] = 'query_failed'
        results.append(item)
    report = {
        'complete': all('error' not in item for item in results),
        'relations': results,
    }
    try:
        report['unknown_target_types'] = _unknown_discriminator_counts(connection)['unknown_target_types']
    except Exception:
        report['unknown_target_types'] = None
        report['complete'] = False
    try:
        report['unknown_point_log_types'] = _unknown_point_log_types(connection)['unknown_point_log_types']
    except Exception:
        report['unknown_point_log_types'] = None
        report['complete'] = False
    return report


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse 的错误详情可能原样包含调用者误传的 URL 或凭据。
        self.print_usage(sys.stderr)
        self.exit(2, '参数错误，请使用 --help 查看用法。\n')


def main(argv=None):
    parser = _SafeArgumentParser(description='只读数据库关系清单与孤儿统计')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--inventory', action='store_true', help='仅打印离线关系清单')
    group.add_argument('--database-url-env', metavar='ENV', help='显式指定保存数据库 URL 的环境变量名')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if args.inventory:
        print(json.dumps([asdict(r) for r in RELATIONS], ensure_ascii=False, indent=2))
        return 0
    url = os.environ.get(args.database_url_env, '')
    try:
        parsed = make_url(url)
        # 驱动查询参数可执行初始化 SQL 或覆盖 host/database/socket 等目标。
        # 不维护易遗漏的黑名单；此工具不接受任何 URL 查询参数。
        # 驱动同样限定为 pymysql：其他 MySQL 驱动对连接参数的处理不同，
        # 无法保证上面两项约束成立。
        # 未配置经验证的 TLS，远程连接无法验证服务器身份，故只允许
        # 显式的 loopback 主机；'localhost' 也拒绝，因为解析结果随系统而异。
        if (parsed.get_backend_name() != 'mysql'
                or parsed.get_driver_name() != 'pymysql'
                or parsed.host not in ('127.0.0.1', '::1')
                or not parsed.host
                or not parsed.database
                or parsed.query):
            raise ValueError('explicit pymysql MySQL database without query parameters required')
        engine = create_engine(parsed, hide_parameters=True)
        try:
            with engine.connect() as connection:
                report = audit_relations(connection)
        finally:
            engine.dispose()
    except Exception:
        print(json.dumps({'complete': False, 'error': 'connection_failed'}), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    sys.exit(main())
