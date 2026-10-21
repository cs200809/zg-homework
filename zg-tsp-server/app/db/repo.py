"""仓储层 —— SQLAlchemy 实现。

方法签名与 P1 的内存版保持一致，因此 routers / services 无需改动。
所有方法均只读或返回 ORM 对象；写操作由调用方控制事务。
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import PointRule, TeacherInviteCode, User


class Repo:
    """仓储。持有会话，由 FastAPI 依赖注入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------- users ----------------

    def add_user(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()  # 回填自增主键
        return user

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_user_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.id)))

    def count_users(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User)) or 0

    # ---------------- 老师邀请码 ----------------

    def add_invite_code(
        self,
        code: str,
        created_by: int,
        expire_at: datetime | None = None,
    ) -> TeacherInviteCode:
        invite = TeacherInviteCode(
            code=code,
            created_by=created_by,
            expire_at=expire_at,
        )
        self.db.add(invite)
        self.db.flush()
        return invite

    def get_invite_by_code(self, code: str) -> TeacherInviteCode | None:
        return self.db.scalar(select(TeacherInviteCode).where(TeacherInviteCode.code == code))

    def list_invite_codes(self) -> list[TeacherInviteCode]:
        return list(self.db.scalars(select(TeacherInviteCode).order_by(TeacherInviteCode.id)))

    # ---------------- 积分规则 ----------------

    def add_point_rule(self, rule: PointRule) -> PointRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_rule_by_key(self, rule_key: str) -> PointRule | None:
        return self.db.scalar(select(PointRule).where(PointRule.rule_key == rule_key))

    def list_point_rules(self) -> list[PointRule]:
        return list(self.db.scalars(select(PointRule).order_by(PointRule.id)))


def get_repo(db: Session) -> Repo:
    """FastAPI 依赖：构造仓储。"""
    return Repo(db)