"""认证相关 Pydantic 出入参（PRD 5.1）。"""

import re

from pydantic import BaseModel, Field, field_validator

from app.models.constants import REGISTERABLE_ROLES

# 手机号（迭代 v2.1：用户名必须是手机号）
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=6, max_length=64)
    role: str
    nickname: str | None = Field(None, max_length=30)
    # 老师注册码：一码一用
    teacher_invite_code: str | None = None
    # 学生注册码：班级邀请码（多学生可用）
    class_invite_code: str | None = None
    # 家长注册码：学生绑定码（多家长可用）
    bind_code: str | None = None

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        if v not in REGISTERABLE_ROLES:
            raise ValueError(
                f"role 必须是 {', '.join(REGISTERABLE_ROLES)} 之一；admin 不开放注册"
            )
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not PHONE_PATTERN.match(v):
            raise ValueError("用户名必须是 11 位手机号")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=64)


class UserInfo(BaseModel):
    """对外暴露的用户信息，绝不含 password_hash。"""

    id: int
    username: str
    role: str
    nickname: str | None = None
    avatar: str | None = None
    class_id: int | None = None
    bind_code: str | None = None
    total_points: int = 0
    must_change_password: bool = False


class LoginResponse(BaseModel):
    token: str
    expire_at: int
    user: UserInfo
    must_change_password: bool = False


class WechatUserInfo(BaseModel):
    """/auth/me 返回体。"""

    user: UserInfo