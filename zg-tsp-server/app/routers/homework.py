"""作业接口（PRD 5.3）。

时间采集（PRD 5.3）：
- 「开始写作业」记录 `start_time`，**重复点击不覆盖**
- 「提交作业」记录 `submit_time`，`duration = submit - start`
- 超截止时间标记 `late`
- 用时 <1 分钟标记待审核（异常）

积分：按时交读 `homework_on_time`，迟交读 `homework_late`（PRD 4.2/第 6 节）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import (
    HOMEWORK_DOING,
    HOMEWORK_LATE,
    HOMEWORK_NOT_STARTED,
    HOMEWORK_SUBMITTED,
    POINT_TYPE_HOMEWORK,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import Homework, HomeworkRecord, User
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok

router = APIRouter(prefix="/homework", tags=["作业"])

# 用时不足 1 分钟视为异常，待老师审核（PRD 5.3）
MIN_DURATION_MINUTES = 1


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _homework_to_dict(hw: Homework) -> dict:
    return {
        "id": hw.id,
        "class_id": hw.class_id,
        "teacher_id": hw.teacher_id,
        "title": hw.title,
        "description": hw.description,
        "subject": hw.subject,
        "deadline": hw.deadline.isoformat() if hw.deadline else None,
        "created_at": hw.created_at.isoformat() if hw.created_at else None,
    }


def _record_to_dict(r: HomeworkRecord) -> dict:
    return {
        "id": r.id,
        "homework_id": r.homework_id,
        "student_id": r.student_id,
        "start_time": r.start_time.isoformat() if r.start_time else None,
        "submit_time": r.submit_time.isoformat() if r.submit_time else None,
        "duration_minutes": r.duration_minutes,
        "status": r.status,
        "file_url": r.file_url,
        "text_content": r.text_content,
        "points": r.points,
        # 用时 <1 分钟标记异常，待老师审核（PRD 5.3）
        "suspicious": bool(
            r.duration_minutes is not None and r.duration_minutes < MIN_DURATION_MINUTES
        ),
    }


def _require_teacher(user: User) -> None:
    if user.role != ROLE_TEACHER:
        raise _forbidden("仅老师可执行此操作")


def _require_student(user: User) -> None:
    if user.role != ROLE_STUDENT:
        raise _forbidden("仅学生可执行此操作")


def _own_class_or_403(db: Session, user: User, class_id: int):
    """确认该班级归当前老师所有。"""
    klass = Repo(db).get_class_by_id(class_id)
    if not klass:
        raise _not_found("班级不存在")
    if klass.teacher_id != user.id:
        raise _forbidden("只能操作自己班级的数据")
    return klass


# ---------------- 出入参 ----------------


class HomeworkCreateRequest(BaseModel):
    class_id: int
    title: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    subject: str | None = Field(None, max_length=20)
    deadline: datetime


class HomeworkListRequest(BaseModel):
    class_id: int
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class HomeworkIdRequest(BaseModel):
    homework_id: int


# ---------------- 接口 ----------------


@router.post("/create")
async def create_homework(
    req: HomeworkCreateRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师布置作业（PRD 5.3）。"""
    _require_teacher(teacher)
    _own_class_or_403(db, teacher, req.class_id)

    hw = Repo(db).add_homework(
        Homework(
            class_id=req.class_id,
            teacher_id=teacher.id,
            title=req.title.strip(),
            description=req.description,
            subject=req.subject,
            deadline=req.deadline,
        )
    )
    db.commit()
    return ok({"homework": _homework_to_dict(hw)})


@router.post("/list")
async def list_homework(
    req: HomeworkListRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师查看本班作业列表（分页）。"""
    _require_teacher(teacher)
    _own_class_or_403(db, teacher, req.class_id)

    items, total = Repo(db).list_homework_paged(req.class_id, req.page, req.size)
    return ok({
        "list": [_homework_to_dict(h) for h in items],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/today")
async def today_homework(
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """学生端「今日作业」（PRD 5.3、9 学生端首页）。"""
    _require_student(student)

    if student.class_id is None:
        return ok({"list": [], "total": 0, "class_id": None})

    items = Repo(db).list_homework_today(student.class_id, datetime.now().date())
    repo = Repo(db)

    # 附带该生当前状态
    result = []
    for hw in items:
        record = repo.get_homework_record(hw.id, student.id)
        item = _homework_to_dict(hw)
        item["my_status"] = record.status if record else HOMEWORK_NOT_STARTED
        item["my_points"] = record.points if record else 0
        result.append(item)

    return ok({"list": result, "total": len(result), "class_id": student.class_id})


@router.post("/detail")
async def homework_detail(
    req: HomeworkIdRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """作业详情。all：老师看自己班的，学生看本班的。"""
    repo = Repo(db)
    hw = repo.get_homework_by_id(req.homework_id)
    if not hw:
        raise _not_found("作业不存在")

    if user.role == ROLE_TEACHER:
        _own_class_or_403(db, user, hw.class_id)
    elif user.role == ROLE_STUDENT:
        if hw.class_id != user.class_id:
            raise _forbidden("不能查看其他班级的作业")

    data = _homework_to_dict(hw)
    if user.role == ROLE_STUDENT:
        record = repo.get_homework_record(hw.id, user.id)
        data["my_record"] = _record_to_dict(record) if record else None
    return ok({"homework": data})


@router.post("/records")
async def homework_records(
    req: HomeworkIdRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师查看作业完成情况：学生、状态、开始时间、提交时间、用时、积分（PRD 5.3）。"""
    _require_teacher(teacher)

    repo = Repo(db)
    hw = repo.get_homework_by_id(req.homework_id)
    if not hw:
        raise _not_found("作业不存在")
    _own_class_or_403(db, teacher, hw.class_id)

    students = repo.list_students_in_class(hw.class_id)
    records = {r.student_id: r for r in repo.list_homework_records(hw.id)}

    rows = []
    for s in students:
        rec = records.get(s.id)
        row = {
            "student_id": s.id,
            "username": s.username,
            "nickname": s.nickname,
            "status": rec.status if rec else HOMEWORK_NOT_STARTED,
            "points": rec.points if rec else 0,
        }
        if rec:
            row.update({
                "start_time": rec.start_time.isoformat() if rec.start_time else None,
                "submit_time": rec.submit_time.isoformat() if rec.submit_time else None,
                "duration_minutes": rec.duration_minutes,
                "file_url": rec.file_url,
                "text_content": rec.text_content,
                "suspicious": bool(
                    rec.duration_minutes is not None
                    and rec.duration_minutes < MIN_DURATION_MINUTES
                ),
            })
        rows.append(row)

    submitted = repo.count_submitted_records(hw.id)
    return ok({
        "homework": _homework_to_dict(hw),
        "records": rows,
        "total_students": len(students),
        "submitted_count": submitted,
    })


@router.post("/delete")
async def delete_homework(
    req: HomeworkIdRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """删除作业 —— 仅无人提交时可删（PRD 5.3）。"""
    _require_teacher(teacher)

    repo = Repo(db)
    hw = repo.get_homework_by_id(req.homework_id)
    if not hw:
        raise _not_found("作业不存在")
    _own_class_or_403(db, teacher, hw.class_id)

    submitted = repo.count_submitted_records(hw.id)
    if submitted > 0:
        raise _bad_request(f"已有 {submitted} 人提交，不可删除")

    # 同时清理未提交的开始记录
    for rec in repo.list_homework_records(hw.id):
        db.delete(rec)
    db.delete(hw)
    db.commit()

    return ok({"deleted_id": req.homework_id})


@router.post("/start")
async def start_homework(
    req: HomeworkIdRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """学生「开始写作业」—— 记录 start_time，**重复点击不覆盖**（PRD 5.3）。"""
    _require_student(student)

    repo = Repo(db)
    hw = repo.get_homework_by_id(req.homework_id)
    if not hw:
        raise _not_found("作业不存在")
    if hw.class_id != student.class_id:
        raise _forbidden("不能操作其他班级的作业")

    record = repo.get_homework_record(hw.id, student.id)
    if record:
        if record.submit_time is not None:
            raise _bad_request("已提交，不可再次开始")
        # 重复点击不覆盖已有的 start_time（PRD 5.3）
        return ok({"record": _record_to_dict(record), "already_started": True})

    record = repo.add_homework_record(
        HomeworkRecord(
            homework_id=hw.id,
            student_id=student.id,
            start_time=datetime.now(),
            status=HOMEWORK_DOING,
        )
    )
    db.commit()
    return ok({"record": _record_to_dict(record), "already_started": False})


@router.post("/submit")
async def submit_homework(
    homework_id: int = Form(...),
    text_content: str | None = Form(None),
    file: UploadFile | None = File(None),
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """学生提交作业（multipart）。

    - 记录 `submit_time`，`duration = submit - start`
    - 超截止时间标记 `late`，否则 `submitted`
    - 按状态读规则发放积分（PRD 4.2）
    """
    _require_student(student)

    repo = Repo(db)
    hw = repo.get_homework_by_id(homework_id)
    if not hw:
        raise _not_found("作业不存在")
    if hw.class_id != student.class_id:
        raise _forbidden("不能操作其他班级的作业")

    if not text_content and not file:
        raise _bad_request("请填写内容或上传文件")

    record = repo.get_homework_record(hw.id, student.id)
    if record and record.submit_time is not None:
        raise _bad_request("已提交，不可重复提交")

    now = datetime.now()
    if not record:
        record = repo.add_homework_record(
            HomeworkRecord(homework_id=hw.id, student_id=student.id)
        )

    record.submit_time = now
    record.text_content = text_content
    record.status = HOMEWORK_LATE if now > hw.deadline else HOMEWORK_SUBMITTED

    # 用时 = 提交时间 - 开始时间（无开始时间则不计算）
    if record.start_time is not None:
        delta = now - record.start_time
        record.duration_minutes = max(0, int(delta.total_seconds() // 60))

    # 文件上传（PRD 10.1：白名单 jpg/png/pdf，≤10MB）
    if file is not None and file.filename:
        record.file_url = await _save_upload(file)

    db.flush()

    # 发放积分：按时交 / 迟交读不同规则（PRD 4.2）
    from app.services import point_service

    rule_key = (
        "homework_late" if record.status == HOMEWORK_LATE else "homework_on_time"
    )
    record.points = point_service.award(
        db,
        student.id,
        POINT_TYPE_HOMEWORK,
        rule_key,
        remark=f"作业：{hw.title}",
        operator_id=student.id,
        # 作业无次数日上限概念，按规则表发放
        enforce_limit=True,
    )

    db.commit()
    return ok({"record": _record_to_dict(record)})


async def _save_upload(file: UploadFile) -> str:
    """保存作业附件，校验扩展名与体积（PRD 10.1）。"""
    from app.config import settings
    from app.utils.upload import save_upload

    return await save_upload(
        file,
        allowed=settings.allowed_extension_list,
        max_mb=settings.max_upload_mb,
    )