"""班级管理接口（PRD 5.2）。

规则：
- 老师创建班级，生成 6 位邀请码
- 学生凭邀请码加入，**一个学生只属一个班级**（决策 3）
- 老师查看本班学生、移除学生（只能操作自己班的）
"""

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import ROLE_STUDENT, ROLE_TEACHER
from app.models.entities import Class, User
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok

router = APIRouter(prefix="/classes", tags=["班级"])

# 班级邀请码 6 位，去掉易混淆字符
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _gen_class_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def _class_to_dict(c: Class, student_count: int | None = None) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "invite_code": c.invite_code,
        "teacher_id": c.teacher_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "student_count": student_count,
    }


def _student_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "total_points": u.total_points,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _require_teacher(user: User) -> None:
    if user.role != ROLE_TEACHER:
        raise _forbidden("仅老师可执行此操作")


# ---------------- 出入参 ----------------


class ClassCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class ClassJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=12)


class ClassStudentsRequest(BaseModel):
    class_id: int


class RemoveStudentRequest(BaseModel):
    class_id: int
    student_id: int


# ---------------- 接口 ----------------


@router.post("/create")
async def create_class(
    req: ClassCreateRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师创建班级，生成 6 位邀请码（PRD 5.2）。"""
    _require_teacher(teacher)

    repo = Repo(db)
    code = _gen_class_code()
    for _ in range(10):
        if not repo.get_class_by_invite_code(code):
            break
        code = _gen_class_code()
    else:
        raise _bad_request("邀请码生成失败，请重试")

    klass = repo.add_class(
        Class(name=req.name.strip(), invite_code=code, teacher_id=teacher.id)
    )
    db.commit()
    return ok({"class": _class_to_dict(klass, 0)})


@router.post("/join")
async def join_class(
    req: ClassJoinRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """学生凭邀请码加入班级（PRD 5.2、决策 3：一个学生只属一个班级）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可加入班级")

    if student.class_id is not None:
        raise _bad_request("已加入班级，不能重复加入")

    repo = Repo(db)
    klass = repo.get_class_by_invite_code(req.invite_code.strip().upper())
    if not klass:
        raise _not_found("班级邀请码不存在")

    student.class_id = klass.id
    db.commit()

    return ok({"class": _class_to_dict(klass)})


@router.post("/my")
async def my_class(user: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    """当前用户的班级信息：老师返回自己建的班，学生返回所属班。"""
    repo = Repo(db)

    if user.role == ROLE_TEACHER:
        classes = repo.list_classes_by_teacher(user.id)
        counts = repo.count_students_by_class()
        return ok({
            "role": ROLE_TEACHER,
            "classes": [_class_to_dict(c, counts.get(c.id, 0)) for c in classes],
        })

    if user.role == ROLE_STUDENT:
        if user.class_id is None:
            return ok({"role": ROLE_STUDENT, "classes": []})
        klass = repo.get_class_by_id(user.class_id)
        if not klass:
            return ok({"role": ROLE_STUDENT, "classes": []})
        return ok({
            "role": ROLE_STUDENT,
            "classes": [_class_to_dict(klass)],
        })

    # admin / parent 不参与班级
    return ok({"role": user.role, "classes": []})


@router.post("/students")
async def class_students(
    req: ClassStudentsRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师查看本班学生（PRD 5.2）。只能查看自己班的。"""
    _require_teacher(teacher)

    repo = Repo(db)
    klass = repo.get_class_by_id(req.class_id)
    if not klass:
        raise _not_found("班级不存在")
    if klass.teacher_id != teacher.id:
        raise _forbidden("只能查看自己班级的学生")

    students = repo.list_students_in_class(req.class_id)
    return ok({
        "class": _class_to_dict(klass, len(students)),
        "students": [_student_to_dict(s) for s in students],
    })


@router.post("/remove-student")
async def remove_student(
    req: RemoveStudentRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师从自己班级移除学生（PRD 5.2）。"""
    _require_teacher(teacher)

    repo = Repo(db)
    klass = repo.get_class_by_id(req.class_id)
    if not klass:
        raise _not_found("班级不存在")
    if klass.teacher_id != teacher.id:
        raise _forbidden("只能操作自己班级的学生")

    student = repo.get_user_by_id(req.student_id)
    if not student:
        raise _not_found("学生不存在")
    if student.class_id != req.class_id:
        raise _bad_request("该学生不属于此班级")

    student.class_id = None
    db.commit()

    return ok({"removed_student_id": student.id, "class_id": req.class_id})