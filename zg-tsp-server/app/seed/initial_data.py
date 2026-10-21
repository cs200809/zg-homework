"""启动种子（PRD 10.4）。

- 若无 admin 则创建：用户名 `admin`，密码取 ADMIN_INIT_PASSWORD，缺省随机生成并打印日志
- 积分规则种子（PRD 4.2）：已存在则跳过
- 附加：为联调预置各角色测试账号与一个未使用的老师邀请码
"""

import json
import logging
import secrets

from app.db.repo import repo
from app.models.entities import (
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
    PointRule,
    User,
)
from app.utils.security import hash_password

logger = logging.getLogger(__name__)

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

# 联调用测试账号（密码统一，登录后应改密）
TEST_PASSWORD = "test123456"
TEST_ACCOUNTS = [
    ("teacher01", ROLE_TEACHER, "王老师"),
    ("student01", ROLE_STUDENT, "张小明"),
    ("student02", ROLE_STUDENT, "李小红"),
    ("parent01", ROLE_PARENT, "张爸爸"),
]

# 预置一个未使用的老师邀请码，便于联调
DEV_INVITE_CODE = "TEACH2024"


def seed_admin() -> User:
    """创建初始 admin。若已存在则直接返回。"""
    existing = repo.get_user_by_username("admin")
    if existing:
        return existing

    from app.config import settings

    password = settings.admin_init_password or secrets.token_urlsafe(12)
    admin = repo.add_user(
        User(
            id=0,
            username="admin",
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
            nickname="超级管理员",
            # 首登强制改密（PRD 5.1）
            must_change_password=True,
        )
    )

    if settings.admin_init_password:
        logger.info("已创建初始 admin，密码取自 ADMIN_INIT_PASSWORD 环境变量")
    else:
        logger.warning(
            "已创建初始 admin，密码（随机生成，仅本次显示）：%s —— 请立即登录并修改",
            password,
        )
    return admin


def seed_point_rules() -> int:
    """写入积分规则种子，已存在则跳过。返回新增条数。"""
    created = 0
    for key, name, points, daily_limit, extra in DEFAULT_POINT_RULES:
        if repo.get_rule_by_key(key):
            continue
        repo.add_point_rule(
            PointRule(
                id=0,
                rule_key=key,
                rule_name=name,
                points=points,
                daily_limit=daily_limit,
                extra_config=json.dumps(extra, ensure_ascii=False) if extra else None,
            )
        )
        created += 1
    return created


def seed_dev_accounts(admin_id: int) -> None:
    """联调用测试账号与邀请码。仅在无任何用户时执行。"""
    if repo.count_users() > 1:
        return

    password_hash = hash_password(TEST_PASSWORD)
    for username, role, nickname in TEST_ACCOUNTS:
        repo.add_user(
            User(
                id=0,
                username=username,
                password_hash=password_hash,
                role=role,
                nickname=nickname,
                # 学生绑定码：家长端绑定用
                bind_code=f"B{username[-2:]}01" if role == ROLE_STUDENT else None,
                total_points=50 if role == ROLE_STUDENT else 0,
            )
        )

    repo.add_invite_code(code=DEV_INVITE_CODE, created_by=admin_id)

    logger.info("已创建联调测试账号（密码 %s）：%s", TEST_PASSWORD,
                "、".join(u for u, _, _ in TEST_ACCOUNTS))
    logger.info("已预置老师邀请码：%s", DEV_INVITE_CODE)


def seed_all() -> None:
    """执行全部种子。"""
    admin = seed_admin()
    rules = seed_point_rules()
    seed_dev_accounts(admin.id)
    logger.info("种子完成：admin=%s，积分规则新增 %d 条", admin.username, rules)