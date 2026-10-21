"""内存数据模型（Mock 层）。

对应 PRD 第 4 节的建表 SQL，但暂不落库 —— 用 dataclass + 内存列表承载，
接口层通过 `app.db.repo` 访问。后续接入 SQLAlchemy 时只需替换 repo 实现，
routers / services 的调用签名保持不变。
"""

from dataclasses import dataclass, field
from datetime import datetime

# --- 枚举常量（PRD 4.1 注释中的取值）---
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_PARENT = "parent"
ALL_ROLES = (ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT)

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

INVITE_UNUSED = "unused"
INVITE_USED = "used"
INVITE_EXPIRED = "expired"
INVITE_REVOKED = "revoked"


def _now() -> datetime:
    return datetime.now()


@dataclass
class User:
    """users 表。"""

    id: int
    username: str
    password_hash: str
    role: str
    nickname: str | None = None
    avatar: str | None = None
    class_id: int | None = None
    bind_code: str | None = None  # 学生绑定码（家长绑定用）
    total_points: int = 0
    status: str = STATUS_ACTIVE
    must_change_password: bool = False
    created_at: datetime = field(default_factory=_now)


@dataclass
class TeacherInviteCode:
    """teacher_invite_codes 表 —— admin 发放，一码一用。"""

    id: int
    code: str
    status: str = INVITE_UNUSED
    created_by: int = 0
    used_by_user_id: int | None = None
    expire_at: datetime | None = None
    created_at: datetime = field(default_factory=_now)
    used_at: datetime | None = None


@dataclass
class PointRule:
    """point_rules 表 —— admin 可改，动态生效。"""

    id: int
    rule_key: str
    rule_name: str
    points: int
    daily_limit: int | None = None
    extra_config: str | None = None  # JSON
    enabled: bool = True
    updated_by: int | None = None
    updated_at: datetime = field(default_factory=_now)


# P1 只建认证相关实体；其余表在对应 Phase 补齐。