"""超级管理员接口（PRD 5.8.1、5.8.2、5.8.5）。

关键规则：
- 敏感操作写 `admin_logs`（PRD 10.1）
- **admin 账号不可被禁用/启用/重置密码**（含 admin 自己），返回 400（PRD 5.8.2）
- 禁用立即生效：JWT 依赖每次查库校验 status（PRD 3.3）
"""

import secrets
import string
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import (
    INVITE_REVOKED,
    INVITE_UNUSED,
    ROLE_ADMIN,
    STATUS_ACTIVE,
    STATUS_DISABLED,
)
from app.models.entities import User
from app.schemas.admin import (
    AdminUserItem,
    ClassListRequest,
    InviteCreateRequest,
    InviteItem,
    InviteListRequest,
    InviteRevokeRequest,
    UserActionRequest,
    UserDetailRequest,
    UserListRequest,
)
from app.utils.deps import require_admin
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok
from app.utils.security import hash_password

router = APIRouter(prefix="/admin", tags=["管理员"], dependencies=[Depends(require_admin)])

# 邀请码字符集：去掉易混淆的 0/O、1/I/l
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _gen_code(length: int = 12) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def _gen_temp_password(length: int = 10) -> str:
    """重置密码用的临时密码，避免易混淆字符。"""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def _invite_to_item(inv) -> dict:
    return InviteItem(
        id=inv.id,
        code=inv.code,
        status=inv.status,
        created_by=inv.created_by,
        used_by_user_id=inv.used_by_user_id,
        expire_at=inv.expire_at,
        created_at=inv.created_at,
        used_at=inv.used_at,
    ).model_dump()


def _user_to_item(u: User) -> dict:
    """admin 视角的用户信息。不含 password_hash。"""
    return AdminUserItem(
        id=u.id,
        username=u.username,
        role=u.role,
        nickname=u.nickname,
        avatar=u.avatar,
        class_id=u.class_id,
        bind_code=u.bind_code,
        total_points=u.total_points,
        status=u.status,
        must_change_password=u.must_change_password,
        created_at=u.created_at,
    ).model_dump()


def _protect_admin(target: User) -> None:
    """admin 账号不可被其他 admin 操作（PRD 5.8.2、8、第 12 节验收）。"""
    if target.role == ROLE_ADMIN:
        raise _bad_request("不可操作 admin 账号")


# ==================== 5.8.1 老师邀请码管理 ====================


@router.post("/invite/create")
async def invite_create(
    req: InviteCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量生成老师邀请码（1~50 个），有效期默认 7 天。"""
    repo = Repo(db)
    expire_at = datetime.now() + timedelta(days=req.expire_days)

    # 极小概率随机碰撞，重试直到唯一
    codes: list[str] = []
    for _ in range(req.count):
        for _attempt in range(10):
            code = _gen_code()
            if not repo.get_invite_by_code(code):
                codes.append(code)
                break
        else:
            raise _bad_request("邀请码生成失败，请重试")

    for code in codes:
        repo.add_invite_code(code=code, created_by=admin.id, expire_at=expire_at)

    repo.add_admin_log(
        admin_id=admin.id,
        action="invite_create",
        target_type="teacher_invite_code",
        detail=f"批量生成 {req.count} 个邀请码，有效期 {req.expire_days} 天",
    )
    db.commit()

    return ok({"codes": codes, "count": len(codes), "expire_at": expire_at.isoformat()})


@router.post("/invite/list")
async def invite_list(
    req: InviteListRequest,
    db: Session = Depends(get_db),
):
    """邀请码列表（可按状态筛选），分页。"""
    repo = Repo(db)
    items, total = repo.list_invite_codes_paged(req.status, req.page, req.size)
    return ok({
        "list": [_invite_to_item(i) for i in items],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/invite/revoke")
async def invite_revoke(
    req: InviteRevokeRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """撤销未使用的邀请码。已使用/已撤销的拒绝。"""
    repo = Repo(db)
    invite = repo.get_invite_by_id(req.code_id)
    if not invite:
        raise _not_found("邀请码不存在")

    if invite.status != INVITE_UNUSED:
        raise _bad_request(f"只能撤销未使用的邀请码（当前状态：{invite.status}）")

    invite.status = INVITE_REVOKED
    repo.add_admin_log(
        admin_id=admin.id,
        action="invite_revoke",
        target_type="teacher_invite_code",
        target_id=invite.id,
        detail=f"撤销邀请码 {invite.code}",
    )
    db.commit()

    return ok({"code_id": invite.id, "status": invite.status})


# ==================== 5.8.2 用户管理 ====================


@router.post("/users/list")
async def users_list(req: UserListRequest, db: Session = Depends(get_db)):
    """用户列表：角色/状态筛选 + 关键词搜索 + 分页。"""
    repo = Repo(db)
    items, total = repo.list_users_paged(req.role, req.status, req.keyword, req.page, req.size)
    return ok({
        "list": [_user_to_item(u) for u in items],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/users/detail")
async def users_detail(req: UserDetailRequest, db: Session = Depends(get_db)):
    """用户详情。"""
    user = Repo(db).get_user_by_id(req.user_id)
    if not user:
        raise _not_found("用户不存在")
    return ok({"user": _user_to_item(user)})


@router.post("/users/disable")
async def users_disable(
    req: UserActionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """禁用 teacher/student/parent。不可操作 admin（含自己）。"""
    repo = Repo(db)
    target = repo.get_user_by_id(req.user_id)
    if not target:
        raise _not_found("用户不存在")

    _protect_admin(target)

    if target.status == STATUS_DISABLED:
        raise _bad_request("用户已是禁用状态")

    target.status = STATUS_DISABLED
    repo.add_admin_log(
        admin_id=admin.id,
        action="user_disable",
        target_type="user",
        target_id=target.id,
        detail=f"禁用用户 {target.username}（{target.role}）",
    )
    db.commit()

    return ok({"user_id": target.id, "status": target.status})


@router.post("/users/enable")
async def users_enable(
    req: UserActionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """启用 teacher/student/parent。不可操作 admin（含自己）。"""
    repo = Repo(db)
    target = repo.get_user_by_id(req.user_id)
    if not target:
        raise _not_found("用户不存在")

    _protect_admin(target)

    if target.status == STATUS_ACTIVE:
        raise _bad_request("用户已是启用状态")

    target.status = STATUS_ACTIVE
    repo.add_admin_log(
        admin_id=admin.id,
        action="user_enable",
        target_type="user",
        target_id=target.id,
        detail=f"启用用户 {target.username}（{target.role}）",
    )
    db.commit()

    return ok({"user_id": target.id, "status": target.status})


@router.post("/users/reset-password")
async def users_reset_password(
    req: UserActionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """重置密码：生成临时密码并强制改密。不可操作 admin。"""
    repo = Repo(db)
    target = repo.get_user_by_id(req.user_id)
    if not target:
        raise _not_found("用户不存在")

    _protect_admin(target)

    temp_password = _gen_temp_password()
    target.password_hash = hash_password(temp_password)
    target.must_change_password = True

    repo.add_admin_log(
        admin_id=admin.id,
        action="user_reset_password",
        target_type="user",
        target_id=target.id,
        detail=f"重置用户 {target.username}（{target.role}）密码并强制改密",
    )
    db.commit()

    return ok({"user_id": target.id, "temp_password": temp_password})


# ==================== 5.8.5 班级与全局统计 ====================


@router.post("/classes/list")
async def classes_list(req: ClassListRequest, db: Session = Depends(get_db)):
    """班级列表（分页），含班主任姓名与学生数。"""
    repo = Repo(db)
    items, total = repo.list_classes_paged(req.page, req.size)

    teacher_names = {u.id: (u.nickname or u.username) for u in repo.list_users()}
    student_counts = repo.count_students_by_class()

    return ok({
        "list": [
            {
                "id": c.id,
                "name": c.name,
                "invite_code": c.invite_code,
                "teacher_id": c.teacher_id,
                "teacher_name": teacher_names.get(c.teacher_id),
                "student_count": student_counts.get(c.id, 0),
                "created_at": c.created_at,
            }
            for c in items
        ],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/stats/overview")
async def stats_overview(db: Session = Depends(get_db)):
    """全局数据概览（PRD 5.8.5）。

    无入参接口：不声明 Body 依赖，客户端传空 Body `{}` 或完全不传均可。
    """
    repo = Repo(db)
    return ok({
        "user_count": repo.count_users(),
        "active_user_count": repo.count_active_users(),
        "admin_count": repo.count_by_role(ROLE_ADMIN),
        "teacher_count": repo.count_by_role("teacher"),
        "student_count": repo.count_by_role("student"),
        "parent_count": repo.count_by_role("parent"),
        "class_count": repo.count_classes(),
        "homework_count": repo.count_homework(),
        "point_total": repo.sum_points(),
        "point_log_count": repo.count_point_logs(),
    })