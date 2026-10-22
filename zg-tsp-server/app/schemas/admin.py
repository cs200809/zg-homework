"""admin 端 Pydantic 出入参（PRD 5.8.1、5.8.2、5.8.5）。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.constants import (
    ALL_ROLES,
    INVITE_EXPIRED,
    INVITE_REVOKED,
    INVITE_UNUSED,
    INVITE_USED,
    STATUS_ACTIVE,
    STATUS_DISABLED,
)


class PageRequest(BaseModel):
    """分页请求基类（PRD 3.2）。"""

    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


# ---------------- 邀请码 ----------------


class InviteCreateRequest(BaseModel):
    count: int = Field(..., ge=1, le=50)  # 批量 1~50 个
    expire_days: int = Field(7, ge=1, le=365)  # 有效期默认 7 天


class InviteListRequest(PageRequest):
    status: str | None = None

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str | None) -> str | None:
        allowed = (INVITE_UNUSED, INVITE_USED, INVITE_EXPIRED, INVITE_REVOKED)
        if v is not None and v not in allowed:
            raise ValueError(f"status 必须是 {', '.join(allowed)} 之一")
        return v


class InviteRevokeRequest(BaseModel):
    code_id: int


# ---------------- 用户管理 ----------------


class UserListRequest(PageRequest):
    role: str | None = None
    status: str | None = None
    keyword: str | None = None

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ALL_ROLES:
            raise ValueError(f"role 必须是 {', '.join(ALL_ROLES)} 之一")
        return v

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str | None) -> str | None:
        if v is not None and v not in (STATUS_ACTIVE, STATUS_DISABLED):
            raise ValueError(f"status 必须是 {STATUS_ACTIVE} 或 {STATUS_DISABLED}")
        return v


class UserActionRequest(BaseModel):
    """禁用/启用/重置密码/详情的公共入参。"""

    user_id: int


class UserDetailRequest(BaseModel):
    user_id: int


class ClassListRequest(PageRequest):
    pass


# ---------------- 出参 ----------------


class InviteItem(BaseModel):
    id: int
    code: str
    status: str
    created_by: int
    used_by_user_id: int | None = None
    expire_at: datetime | None = None
    created_at: datetime
    used_at: datetime | None = None


class AdminUserItem(BaseModel):
    """admin 看到的用户信息。含 bind_code / total_points，不含 password_hash。"""

    id: int
    username: str
    role: str
    nickname: str | None = None
    avatar: str | None = None
    class_id: int | None = None
    bind_code: str | None = None
    total_points: int
    status: str
    must_change_password: bool
    created_at: datetime


class PagedResponse(BaseModel):
    """分页响应（PRD 3.2）：{list, total, page, size}。"""

    list: list
    total: int
    page: int
    size: int