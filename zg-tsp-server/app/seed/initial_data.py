"""数据库初始化与种子数据（PRD 10.4、4.2）。

- 建表：SQLAlchemy create_all，幂等
- admin 种子：若无则创建，密码取 ADMIN_INIT_PASSWORD，缺省随机生成并打印日志
- 积分规则种子：PRD 4.2 的 10 条默认规则，已存在则跳过
- 联调数据：一个班级、四角色测试账号、家长绑定关系、老师邀请码

执行方式：
    python -m app.seed.initial_data          # 建表 + 种子
    python -m app.seed.initial_data --reset  # 先删表再建表（危险，仅开发用）
"""

import argparse
import json
import logging
import secrets
import sys
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.db.repo import Repo
from app.db.session import SessionLocal, engine
from app.models.constants import (
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import (
    Base,
    Class,
    IdiomQuestion,
    ParentStudent,
    PointRule,
    TeacherInviteCode,
    User,
)
from app.utils.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- 基础数据定义 ---

# PRD 4.2 积分规则种子
DEFAULT_POINT_RULES = [
    ("checkin_daily", "每日签到", 5, 1, None),
    ("checkin_streak_7", "连续签到7天", 10, 1, None),
    ("homework_on_time", "作业按时提交", 10, None, None),
    ("homework_late", "作业迟交", 5, None, None),
    ("reading_per_minute", "阅读每分钟", 1, 30, {"single_article_limit": 10}),
    ("reading_finish", "读完文章", 5, None, None),
    ("game_sudoku_easy", "数独-简单", 5, 20, None),
    ("game_sudoku_medium", "数独-中等", 10, 20, None),
    ("game_sudoku_hard", "数独-困难", 15, 20, None),
    ("game_idiom", "成语接龙每题", 1, 20, None),
]

# 联调账号（PRD 12 节验收用）
TEST_PASSWORD = "test123456"
TEST_ACCOUNTS = [
    ("teacher01", ROLE_TEACHER, "王老师"),
    ("student01", ROLE_STUDENT, "张小明"),
    ("student02", ROLE_STUDENT, "李小红"),
    ("parent01", ROLE_PARENT, "张爸爸"),
]

DEV_INVITE_CODE = "TEACH2024"
DEV_CLASS_NAME = "三年二班"
DEV_CLASS_INVITE = "CLS2024"

# 成语接龙题库样例（决策 4：正式题库由 admin 后台导入，此处仅少量联调数据）
SAMPLE_IDIOMS = [
    ("画蛇添足", "画蛇添足"),
    ("守株待兔", "守株待兔"),
    ("亡羊补牢", "亡羊补牢"),
    ("井底之蛙", "井底之蛙"),
    ("掩耳盗铃", "掩耳盗铃"),
    ("刻舟求剑", "刻舟求剑"),
    ("狐假虎威", "狐假虎威"),
    ("自相矛盾", "自相矛盾"),
    ("对牛弹琴", "对牛弹琴"),
    ("滥竽充数", "滥竽充数"),
]


def create_tables() -> None:
    """建表（幂等）。"""
    Base.metadata.create_all(bind=engine)
    logger.info("建表完成，共 %d 张表", len(Base.metadata.tables))


def drop_tables() -> None:
    """删表（危险，仅 --reset 使用）。"""
    Base.metadata.drop_all(bind=engine)
    logger.warning("已删除全部表")


def seed_admin(db: Session) -> tuple[User, bool]:
    """创建初始 admin。若已存在则原样返回。返回 (user, 是否新建)。"""
    repo = Repo(db)
    existing = repo.get_user_by_username("admin")
    if existing:
        logger.info("admin 已存在，跳过")
        return existing, False

    password = settings.admin_init_password or secrets.token_urlsafe(12)
    admin = repo.add_user(
        User(
            username="admin",
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            nickname="超级管理员",
            must_change_password=True,  # 首登强制改密（PRD 5.1）
        )
    )

    if settings.admin_init_password:
        logger.info("已创建 admin，密码取自 ADMIN_INIT_PASSWORD")
    else:
        logger.warning(
            "已创建 admin，随机密码（仅本次显示）：%s —— 请立即登录并修改", password
        )
    return admin, True


def seed_point_rules(db: Session) -> int:
    """写入积分规则种子，已存在则跳过。返回新增条数。"""
    repo = Repo(db)
    created = 0
    for key, name, points, daily_limit, extra in DEFAULT_POINT_RULES:
        if repo.get_rule_by_key(key):
            continue
        repo.add_point_rule(
            PointRule(
                rule_key=key,
                rule_name=name,
                points=points,
                daily_limit=daily_limit,
                extra_config=json.dumps(extra, ensure_ascii=False) if extra else None,
            )
        )
        created += 1
    if created:
        logger.info("积分规则新增 %d 条", created)
    return created


def seed_class(db: Session, teacher: User) -> Class | None:
    """创建一个联调班级。"""
    existing = db.query(Class).filter(Class.name == DEV_CLASS_NAME).first()
    if existing:
        return existing

    klass = Class(
        name=DEV_CLASS_NAME,
        invite_code=DEV_CLASS_INVITE,
        teacher_id=teacher.id,
    )
    db.add(klass)
    db.flush()
    logger.info("已创建班级 %s（邀请码 %s）", klass.name, klass.invite_code)
    return klass


def seed_dev_accounts(db: Session, admin: User, klass: Class | None) -> None:
    """联调测试账号、家长绑定、邀请码、成语题库样例。"""
    repo = Repo(db)

    if repo.count_users() > 1:
        logger.info("已存在业务账号，跳过联调数据")
        return

    password_hash = hash_password(TEST_PASSWORD)
    created: dict[str, User] = {}

    for username, role, nickname in TEST_ACCOUNTS:
        user = repo.add_user(
            User(
                username=username,
                password_hash=password_hash,
                role=role,
                nickname=nickname,
                bind_code=f"B{username[-2:]}01" if role == ROLE_STUDENT else None,
                total_points=50 if role == ROLE_STUDENT else 0,
            )
        )
        created[username] = user

    # 学生归入班级
    if klass:
        for username in ("student01", "student02"):
            created[username].class_id = klass.id

    # 家长绑定学生01
    if "parent01" in created and "student01" in created:
        db.add(
            ParentStudent(
                parent_id=created["parent01"].id,
                student_id=created["student01"].id,
            )
        )

    # 老师邀请码（未使用）
    if not repo.get_invite_by_code(DEV_INVITE_CODE):
        repo.add_invite_code(
            code=DEV_INVITE_CODE,
            created_by=admin.id,
            expire_at=datetime.now() + timedelta(days=7),
        )

    # 成语题库样例
    for prompt, answer in SAMPLE_IDIOMS:
        db.add(
            IdiomQuestion(
                prompt=prompt,
                answer=answer,
                distractors=json.dumps(["掩耳盗铃", "刻舟求剑"], ensure_ascii=False),
                created_by=admin.id,
            )
        )

    db.flush()
    logger.info("已创建联调账号（密码 %s）：%s", TEST_PASSWORD,
                "、".join(u for u, _, _ in TEST_ACCOUNTS))
    logger.info("已预置老师邀请码 %s、班级邀请码 %s、成语题库 %d 条",
                DEV_INVITE_CODE, DEV_CLASS_INVITE, len(SAMPLE_IDIOMS))


def run_seed(reset: bool = False) -> None:
    """完整初始化流程。"""
    if reset:
        drop_tables()

    create_tables()

    db = SessionLocal()
    try:
        admin, _ = seed_admin(db)
        seed_point_rules(db)
        klass = seed_class(db, admin)
        seed_dev_accounts(db, admin, klass)
        db.commit()
        logger.info("初始化完成")
    except Exception:
        db.rollback()
        logger.exception("初始化失败，已回滚")
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="数据库初始化与种子数据")
    parser.add_argument("--reset", action="store_true", help="先删除全部表再重建（危险）")
    args = parser.parse_args()

    run_seed(reset=args.reset)
    sys.exit(0)


if __name__ == "__main__":
    main()