"""认证接口（PRD 5.1）。

全 POST + Body，URL 不携带业务参数。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import (
    INVITE_UNUSED,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
    STATUS_ACTIVE,
)
from app.models.entities import ParentStudent, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserInfo,
)
from app.utils.codes import gen_bind_code
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
    return gen_bind_code()


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册。学生/家长/老师（PRD 5.1、迭代 v2.1）。

    - 老师：老师邀请码，**一码一用**
    - 学生：班级邀请码，**多学生可用**，注册后自动入班
    - 家长：学生绑定码，**多家长可用**，注册后自动绑定
    """
    repo = Repo(db)

    if repo.get_user_by_username(req.username):
        raise _bad_request("用户名已存在")

    klass = None
    student = None
    invite = None

    # 老师：校验邀请码（存在 / 未使用 / 未过期）
    if req.role == ROLE_TEACHER:
        if not req.teacher_invite_code:
            raise _bad_request("老师注册必须携带邀请码")

        invite = repo.get_invite_for_update(code=req.teacher_invite_code.strip())
        if not invite:
            raise _bad_request("邀请码不存在")

        if invite.status == INVITE_UNUSED:
            if invite.expire_at and invite.expire_at < datetime.now():
                raise _bad_request("邀请码已过期")
        else:
            raise _bad_request(f"邀请码不可用（状态：{invite.status}）")

    # 学生：班级邀请码（多学生可用，不消耗）
    elif req.role == ROLE_STUDENT:
        if not req.class_invite_code:
            raise _bad_request("学生注册必须携带班级邀请码")
        klass = repo.get_class_by_code_for_update(req.class_invite_code.strip().upper())
        if not klass:
            raise _bad_request("班级邀请码不存在")

    # 家长：学生绑定码（多家长可用，不消耗）
    elif req.role == ROLE_PARENT:
        if not req.bind_code:
            raise _bad_request("家长注册必须携带学生绑定码")
        student = repo.get_student_by_code_for_update(req.bind_code)
        if not student:
            raise _bad_request("学生绑定码不存在")

    try:
        created = repo.add_user(
            User(
                username=req.username,
                password_hash=hash_password(req.password),
                role=req.role,
                nickname=req.nickname or req.username,
                class_id=klass.id if klass else None,
                bind_code=gen_bind_code() if req.role == ROLE_STUDENT else None,
            )
        )
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, 'args', [None])[0] not in (1062, 2067, 1555) and 'UNIQUE constraint failed' not in str(exc.orig):
            raise
        raise _bad_request("用户名或绑定码冲突，请重试") from exc

    # 一码一用：标记老师邀请码已使用
    if invite is not None:
        invite.status = "used"
        invite.used_by_user_id = created.id
        invite.used_at = datetime.now()

    # 家长注册即绑定学生（多家长可用）
    if student is not None:
        repo.add_parent_student(ParentStudent(parent_id=created.id, student_id=student.id))

    db.commit()
    db.refresh(created)

    return ok({"user": _to_user_info(created).model_dump()})


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """登录。返回 JWT 与用户信息。"""
    user = Repo(db).get_user_by_username(req.username.strip())
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改密码。admin 首登后必须调用此接口改密。"""
    if not verify_password(req.old_password, user.password_hash):
        raise _bad_request("原密码错误")

    if req.old_password == req.new_password:
        raise _bad_request("新密码不能与原密码相同")

    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False
    db.commit()

    return ok({"message": "密码修改成功"})


@router.post("/logout")
async def logout():
    """登出。JWT 无状态，服务端不维护会话，由客户端清除 token。"""
    return ok({"message": "已登出"})