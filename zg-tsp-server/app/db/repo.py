"""仓储层 —— SQLAlchemy 实现。

方法签名与 P1 的内存版保持一致，因此 routers / services 无需改动。
所有方法均只读或返回 ORM 对象；写操作由调用方控制事务。
"""

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AdminLog,
    Class,
    Homework,
    PointLog,
    PointRule,
    TeacherInviteCode,
    User,
)


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

    def list_users_paged(
        self,
        role: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[User], int]:
        """用户分页列表（角色/状态筛选 + 关键词搜索）。返回 (当前页, 总数)。

        keyword 同时匹配 username 与 nickname（PRD 5.8.2「搜索」）。
        """
        stmt: Select = select(User)
        count_stmt = select(func.count()).select_from(User)

        conditions = []
        if role:
            conditions.append(User.role == role)
        if status:
            conditions.append(User.status == status)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(User.username.like(like), User.nickname.like(like)))

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(User.id).offset((page - 1) * size).limit(size)
        return list(self.db.scalars(stmt)), total

    # ---------------- 审计日志 ----------------

    def add_admin_log(
        self,
        admin_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: str | None = None,
    ) -> AdminLog:
        log = AdminLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
        self.db.add(log)
        self.db.flush()
        return log

    # ---------------- 统计（PRD 5.8.5） ----------------

    def count_by_role(self, role: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(User).where(User.role == role)
        ) or 0

    def count_active_users(self) -> int:
        return self.db.scalar(
            select(func.count()).select_from(User).where(User.status == "active")
        ) or 0

    def count_classes(self) -> int:
        return self.db.scalar(select(func.count()).select_from(Class)) or 0

    def count_homework(self) -> int:
        return self.db.scalar(select(func.count()).select_from(Homework)) or 0

    def sum_points(self) -> int:
        return self.db.scalar(
            select(func.coalesce(func.sum(User.total_points), 0)).where(User.role == "student")
        ) or 0

    def count_point_logs(self) -> int:
        return self.db.scalar(select(func.count()).select_from(PointLog)) or 0

    def list_classes_paged(self, page: int = 1, size: int = 20) -> tuple[list[Class], int]:
        total = self.count_classes()
        stmt = (
            select(Class)
            .order_by(Class.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(stmt)), total

    def count_students_by_class(self) -> dict[int, int]:
        """各班级学生数，返回 {class_id: count}。"""
        rows = self.db.execute(
            select(User.class_id, func.count(User.id))
            .where(User.class_id.isnot(None))
            .group_by(User.class_id)
        ).all()
        return {cid: cnt for cid, cnt in rows}

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

    def list_invite_codes_paged(
        self,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[TeacherInviteCode], int]:
        """邀请码分页列表（可按状态筛选）。返回 (当前页, 总数)。"""
        stmt: Select = select(TeacherInviteCode)
        count_stmt = select(func.count()).select_from(TeacherInviteCode)
        if status:
            stmt = stmt.where(TeacherInviteCode.status == status)
            count_stmt = count_stmt.where(TeacherInviteCode.status == status)

        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(TeacherInviteCode.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.scalars(stmt)), total

    def get_invite_by_id(self, invite_id: int) -> TeacherInviteCode | None:
        return self.db.get(TeacherInviteCode, invite_id)

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