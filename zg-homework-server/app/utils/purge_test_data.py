"""开发数据清理。请先备份，在维护窗口停止所有服务及后台写入。

实际执行必须显式传 --maintenance-confirmed，声明在计划和执行全过程停写；
这仅为运维声明，脚本无法自动验证。--yes 不能代替该声明。
保留数据引用待删除对象时停止，不自动修改保留数据。dry-run 不写入。
"""
import argparse
import sys

from sqlalchemy import bindparam, text
from app.db.session import SessionLocal

KEEP_USERNAMES = ('admin', 'teacher01', 'student01', 'student02', 'parent01')
KEEP_CLASS_NAMES = ('三年二班',)
KEEP_CLASS_INVITE_CODES = ('CLS2024',)
KEEP_INVITE_CODES = ('TEACH2024',)

# 关系清单须与模型同步，包括历史多态引用。
RELATIONS = (
    ('users', 'class_id', 'classes', None),
    ('classes', 'teacher_id', 'users', None),
    ('teacher_invite_codes', 'created_by', 'users', None),
    ('teacher_invite_codes', 'used_by_user_id', 'users', None),
    ('homework', 'class_id', 'classes', None),
    ('homework', 'teacher_id', 'users', None),
    ('homework_records', 'homework_id', 'homework', None),
    ('homework_records', 'student_id', 'users', None),
    ('homework_records', 'reviewed_by', 'users', None),
    ('homework_review_rules', 'updated_by', 'users', None),
    ('checkins', 'student_id', 'users', None),
    ('articles', 'author_id', 'users', None),
    ('reading_records', 'article_id', 'articles', None),
    ('reading_records', 'student_id', 'users', None),
    ('game_records', 'student_id', 'users', None),
    ('point_logs', 'student_id', 'users', None),
    ('point_logs', 'operator_id', 'users', None),
    ('parent_students', 'parent_id', 'users', None),
    ('parent_students', 'student_id', 'users', None),
    ('point_rules', 'updated_by', 'users', None),
    ('admin_logs', 'admin_id', 'users', None),
    ('idiom_questions', 'created_by', 'users', None),
    ('admin_logs', 'target_id', 'users', 'user'),
    ('admin_logs', 'target_id', 'teacher_invite_codes', 'teacher_invite_code'),
    ('admin_logs', 'target_id', 'articles', 'article'),
    ('admin_logs', 'target_id', 'idiom_questions', 'idiom_question'),
)


def _selections(by_keep_list):
    if by_keep_list:
        users = 'SELECT id FROM users WHERE username NOT IN :names'
        classes = ('SELECT id FROM classes WHERE invite_code NOT IN :class_codes '
                   'AND NOT (name IN :class_names AND teacher_id = 1)')
        invites = 'SELECT id FROM teacher_invite_codes WHERE code NOT IN :invite_codes'
    else:
        users = ("SELECT id FROM users WHERE username LIKE 'test\\_%' "
                 "OR nickname LIKE 'test\\_%'")
        classes = f'SELECT id FROM classes WHERE teacher_id IN ({users})'
        invites = (f'SELECT id FROM teacher_invite_codes WHERE code LIKE :test_code '
                   f'OR created_by IN ({users})')
    homework = f'SELECT id FROM homework WHERE class_id IN ({classes})'
    articles = f'SELECT id FROM articles WHERE author_id IN ({users})'
    return {
        'users': users, 'classes': classes, 'teacher_invite_codes': invites,
        'homework': homework, 'articles': articles,
        'reading_records': f'SELECT id FROM reading_records WHERE student_id IN ({users}) OR article_id IN ({articles})',
        'homework_records': f'SELECT id FROM homework_records WHERE student_id IN ({users}) OR homework_id IN ({homework})',
        'parent_students': f'SELECT id FROM parent_students WHERE parent_id IN ({users}) OR student_id IN ({users})',
        'game_records': f'SELECT id FROM game_records WHERE student_id IN ({users})',
        'checkins': f'SELECT id FROM checkins WHERE student_id IN ({users})',
        'point_logs': f'SELECT id FROM point_logs WHERE student_id IN ({users})',
        'admin_logs': f'SELECT id FROM admin_logs WHERE admin_id IN ({users})',
        'idiom_questions': f'SELECT id FROM idiom_questions WHERE created_by IN ({users})',
    }


def _statement(sql, params):
    stmt = text(sql)
    for key, value in params.items():
        if isinstance(value, tuple) and f':{key}' in sql:
            stmt = stmt.bindparams(bindparam(key, expanding=True))
    return stmt


def _plan(db, by_keep_list):
    params = {'names': KEEP_USERNAMES, 'class_codes': KEEP_CLASS_INVITE_CODES,
              'class_names': KEEP_CLASS_NAMES, 'invite_codes': KEEP_INVITE_CODES,
              'test_code': 'TEST%'}
    return {table: {row[0] for row in db.execute(_statement(sql, params), params)}
            for table, sql in _selections(by_keep_list).items()}


def _conflicts(db, selected):
    conflicts = []
    known = {'user', 'teacher_invite_code', 'article', 'idiom_question',
             'point_rule', 'homework_review_rule'}
    for source, field, target, kind in RELATIONS:
        ids = selected.get(target, set())
        if not ids:
            continue
        sql = f'SELECT id, {field}' + (', target_type' if kind else '') + f' FROM {source} WHERE {field} IN :ids'
        params = {'ids': tuple(ids)}
        for row in db.execute(_statement(sql, params), params):
            if row[0] in selected.get(source, set()):
                continue
            if kind and row[2] in known and row[2] != kind:
                continue
            conflicts.append(f'{source}.{field} -> {target}')
    # 保留学生的历史记录不能为清理其作业或文章而被级联删除。
    for table in ('reading_records', 'homework_records'):
        ids = selected[table]
        if ids:
            sql = f'SELECT id, student_id FROM {table} WHERE id IN :ids'
            params = {'ids': tuple(ids)}
            if any(row[1] not in selected['users'] for row in db.execute(_statement(sql, params), params)):
                conflicts.append(f'{table}.student_id -> 保留用户的历史记录')
    ids = selected['parent_students']
    if ids:
        sql = 'SELECT parent_id, student_id FROM parent_students WHERE id IN :ids'
        params = {'ids': tuple(ids)}
        if any(parent not in selected['users'] or student not in selected['users']
               for parent, student in db.execute(_statement(sql, params), params)):
            conflicts.append('parent_students -> 保留用户的绑定关系')
    return sorted(set(conflicts))


DELETE_ORDER = ('reading_records', 'homework_records', 'parent_students', 'game_records',
                'checkins', 'point_logs', 'admin_logs', 'idiom_questions',
                'teacher_invite_codes', 'articles', 'homework', 'classes', 'users')


def _purge(db, selected):
    deleted = {}
    for table in DELETE_ORDER:
        ids = selected[table]
        if not ids:
            deleted[table] = 0
            continue
        sql = f'DELETE FROM {table} WHERE id IN :ids'
        params = {'ids': tuple(ids)}
        result = db.execute(_statement(sql, params), params)
        if result.rowcount != len(ids):
            raise RuntimeError(f'{table} 删除数量与计划不一致，事务回滚')
        deleted[table] = result.rowcount
    db.commit()
    return deleted


def _main(argv=None):
    parser = argparse.ArgumentParser(description='清理测试数据；运维须保证维护窗口停写')
    parser.add_argument('--yes', action='store_true', help='跳过删除确认，不代替停写声明')
    parser.add_argument('--dry-run', action='store_true', help='只读计划与冲突检查')
    parser.add_argument('--by-keep-list', action='store_true', help='按种子保留清单清理')
    parser.add_argument('--maintenance-confirmed', action='store_true',
                        help='声明所有服务及后台写入已停止；无法自动验证')
    args = parser.parse_args(argv)
    if not args.dry_run and not args.maintenance_confirmed:
        print('拒绝执行：必须先停写并指定 --maintenance-confirmed；无法自动验证。', file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        selected = _plan(db, args.by_keep_list)
        conflicts = _conflicts(db, selected)
        print('计划清理：')
        for table, ids in selected.items():
            print(f'  {table:24} {len(ids):6} 行')
        if conflicts:
            print('保留对象引用冲突，停止：')
            for conflict in conflicts:
                print(f'  {conflict}')
            return 2
        if args.dry_run:
            print('--dry-run，未做任何改动。')
            return 0
        if not args.yes and input('确认已备份且保持停写，输入 yes 删除：').strip() != 'yes':
            print('已取消。')
            return 1
        deleted = _purge(db, selected)
        print('实际删除：')
        for table, count in deleted.items():
            print(f'  {table:24} {count:6} 行')
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(_main())
