"""内存仓储层（Mock）。

routers / services 只通过本模块的方法访问数据，不直接触碰列表。
后续接入 SQLAlchemy 时替换本文件实现即可，调用方签名不变。

注意：进程内内存，服务重启后数据丢失。适用于 P1 接口联调阶段。
"""

from datetime import datetime, timedelta

from app.models.entities import (
    INVITE_UNUSED,
    STATUS_ACTIVE,
    PointRule,
    TeacherInviteCode,
    User,
)


class MemoryRepo:
    """内存仓储。"""

    def __init__(self) -> None:
        self.users: list[User] = []
        self.invite_codes: list[TeacherInviteCode] = []
        self.point_rules: list[PointRule] = []
        self._next_user_id = 1
        self._next_invite_id = 1
        self._next_rule_id = 1

    def reset(self) -> None:
        """清空全部数据（测试用）。"""
        self.users.clear()
        self.invite_codes.clear()
        self.point_rules.clear()
        self._next_user_id = 1
        self._next_invite_id = 1
        self._next_rule_id = 1

    # ---------------- users ----------------

    def add_user(self, user: User) -> User:
        user.id = self._next_user_id
        self._next_user_id += 1
        self.users.append(user)
        return user

    def get_user_by_id(self, user_id: int) -> User | None:
        return next((u for u in self.users if u.id == user_id), None)

    def get_user_by_username(self, username: str) -> User | None:
        return next((u for u in self.users if u.username == username), None)

    def list_users(self) -> list[User]:
        return list(self.users)

    def count_users(self) -> int:
        return len(self.users)

    # ---------------- 老师邀请码 ----------------

    def add_invite_code(
        self,
        code: str,
        created_by: int,
        expire_at: datetime | None = None,
    ) -> TeacherInviteCode:
        invite = TeacherInviteCode(
            id=self._next_invite_id,
            code=code,
            created_by=created_by,
            expire_at=expire_at,
        )
        self._next_invite_id += 1
        self.invite_codes.append(invite)
        return invite

    def get_invite_by_code(self, code: str) -> TeacherInviteCode | None:
        return next((i for i in self.invite_codes if i.code == code), None)

    def list_invite_codes(self) -> list[TeacherInviteCode]:
        return list(self.invite_codes)

    # ---------------- 积分规则 ----------------

    def add_point_rule(self, rule: PointRule) -> PointRule:
        rule.id = self._next_rule_id
        self._next_rule_id += 1
        self.point_rules.append(rule)
        return rule

    def get_rule_by_key(self, rule_key: str) -> PointRule | None:
        return next((r for r in self.point_rules if r.rule_key == rule_key), None)

    def list_point_rules(self) -> list[PointRule]:
        return list(self.point_rules)


# 全局单例
repo = MemoryRepo()