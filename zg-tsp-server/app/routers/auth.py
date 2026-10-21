"""认证接口（PRD 5.1）。

全 POST + Body，URL 不携带业务参数。
"""

import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.db.repo import repo
from app.models.entities import (
    INVITE_UNUSED,
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TEACHER,
    STATUS_ACTIVE,
    User,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserInfo,
)
from app.utils.deps import get_current_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok
from app.utils.security import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["认证"])


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _to_user_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname,
        avatar=user.avatar,
        class_id=user.class_id,
        bind_code=user.bind_code,
        total_points=user.total_points,
        must_change_password=user.must_change_password,
    )


def _gen_bind_code() -> str:
    """生成学生绑定码（家长绑定用），8 位。"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@router.post("/register")
async def register(req: RegisterRequest):
    """注册。学生/家长/老师；老师必须携带有效邀请码（PRD 5.1）。"""
    if repo.get_user_by_username(req.username):
        raise _bad_request("用户名已存在")

    # 老师：校验邀请码（存在 / 未使用 / 未过期）
    if req.role == ROLE_TEACHER:
        if not req.teacher_invite_code:
            raise _bad_request("老师注册必须携带邀请码")

        invite = repo.get_invite_by_code(req.teacher_invite_code.strip())
        if not invite:
            raise _bad_request("邀请码不存在")

        if invite.status == INVITE_UNUSED:
            if invite.expire_at and invite.expire_at < datetime.now():
                raise _bad_request("邀请码已过期")
        else:
            raise _bad_request(f"邀请码不可用（状态：{invite.status}）")

    user = User(
        id=0,
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        nickname=req.nickname or req.username,
        bind_code=_gen_bind_code() if req.role == ROLE_STUDENT else None,
    )
    created = repo.add_user(user)

    # 一码一用：标记邀请码已使用
    if req.role == ROLE_TEACHER:
        invite.status = "used"
        invite.used_by_user_id = created.id
        invite.used_at = datetime.now()

    return ok({"user": _to_user_info(created).model_dump()})


@router.post("/login")
async def login(req: LoginRequest):
    """登录。返回 JWT 与用户信息。"""
    user = repo.get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user.password_hash):
        raise _bad_request("用户名或密码错误")

    if user.status != STATUS_ACTIVE:
        raise _forbidden("账号已被禁用")

    token, expire_at = create_access_token(user.id, user.role)
    payload = LoginResponse(
        token=token,
        expire_at=expire_at,
        user=_to_user_info(user),
        must_change_password=user.must_change_password,
    )
    return ok(payload.model_dump())


@router.post("/me")
async def me(user: User = Depends(get_current_user)):
    """当前登录用户信息。禁用后立即失效（每次请求查库）。"""
    return ok({"user": _to_user_info(user).model_dump()})


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
):
    """修改密码。admin 首登后必须调用此接口改密。"""
    if not verify_password(req.old_password, user.password_hash):
        raise _bad_request("原密码错误")

    if req.old_password == req.new_password:
        raise _bad_request("新密码不能与原密码相同")

    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False

    return ok({"message": "密码修改成功"})


@router.post("/logout")
async def logout():
    """登出。JWT 无状态，服务端不维护会话，由客户端清除 token。"""
    return ok({"message": "已登出"})