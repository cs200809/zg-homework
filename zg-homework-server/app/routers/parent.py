"""家长端接口（PRD 5.7）。

- 学生生成绑定码，家长输入绑定（可绑多个）
- 查看孩子积分与明细
- 消耗：预设事项（看手机-5、看电视-5、买玩具-20、买零食-10、自定义）
- 校验余额 ≥ 扣分，否则 400
- 写 PointLog（type=consume，points 为负，operator=家长）

权限：家长只能操作**自己绑定**的孩子，跨家长访问返回 403。
"""

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import POINT_TYPE_PARENT_REWARD, ROLE_PARENT, ROLE_STUDENT, HOMEWORK_NOT_STARTED
from app.models.entities import ParentStudent, User
from app.routers.points import RankRequest, rank_response
from app.services import point_service
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok

router = APIRouter(prefix="/parent", tags=["家长"])

# PRD 5.7 预设消耗事项
CONSUME_ITEMS = [
    {"key": "phone", "name": "看手机", "points": 5},
    {"key": "tv", "name": "看电视", "points": 5},
    {"key": "toy", "name": "买玩具", "points": 20},
    {"key": "snack", "name": "买零食", "points": 10},
]

REWARD_ITEMS = [
    {"key": "housework", "name": "主动承担家务", "points": 5},
    {"key": "homework", "name": "积极完成作业", "points": 5},
    {"key": "food", "name": "不挑食", "points": 3},
]


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _require_parent(user: User) -> None:
    if user.role != ROLE_PARENT:
        raise _forbidden("仅家长可使用此接口")


def _own_child(repo: Repo, parent: User, student_id: int) -> User:
    """确认该学生是当前家长的孩子，否则 403（PRD 8）。"""
    child = repo.get_user_by_id(student_id)
    if not child:
        raise _not_found("学生不存在")
    if not repo.get_parent_student(parent.id, student_id):
        raise _forbidden("只能操作自己绑定的孩子")
    return child


# ---------------- 出入参 ----------------


class BindRequest(BaseModel):
    bind_code: str = Field(..., min_length=4, max_length=12)


class ChildPointsRequest(BaseModel):
    student_id: int
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class ChildRankRequest(RankRequest):
    student_id: int


class ConsumeRequest(BaseModel):
    student_id: int
    item: str = Field(..., min_length=1, max_length=50)
    points: int = Field(..., gt=0, le=10000)
    remark: str | None = Field(None, max_length=255)


class RewardRequest(BaseModel):
    student_id: int
    item: str = Field(..., min_length=1, max_length=50)
    points: int = Field(..., gt=0, le=10000)
    remark: str | None = Field(None, max_length=204)


class UnbindRequest(BaseModel):
    student_id: int


class ChildHomeworkListRequest(BaseModel):
    student_id: int
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class ChildHomeworkRequest(BaseModel):
    student_id: int
    homework_id: int


def _homework_child(repo: Repo, parent: User, student_id: int) -> User:
    _require_parent(parent)
    child = _own_child(repo, parent, student_id)
    if child.role != ROLE_STUDENT:
        raise _forbidden("绑定用户不是学生")
    return child


def _child_homework(repo: Repo, child: User, homework_id: int):
    hw = repo.get_homework_by_id(homework_id)
    if not hw:
        raise _not_found("作业不存在")
    if child.class_id is None or hw.class_id != child.class_id:
        raise _forbidden("不能查看其他班级的作业")
    return hw


def _parent_record(record):
    from app.routers.homework import _record_to_dict
    if not record:
        return None
    result = _record_to_dict(record)
    # 不向家长输出旧公开附件地址，也不暴露私有文件名。
    result["file_url"] = "/homework/attachment" if record.file_url else None
    return result


@router.post("/homework/list")
def child_homework_list(req: ChildHomeworkListRequest, parent: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    from app.routers.homework import _homework_to_dict
    repo = Repo(db)
    child = _homework_child(repo, parent, req.student_id)
    result, total = [], 0
    if child.class_id is not None:
        items, total = repo.list_homework_paged(child.class_id, req.page, req.size)
        for hw in items:
            record = repo.get_homework_record(hw.id, child.id)
            item = _homework_to_dict(hw)
            item.update(my_status=record.status if record else HOMEWORK_NOT_STARTED,
                        my_points=record.points if record else 0, my_record=_parent_record(record))
            result.append(item)
    return ok({"list": result, "total": total, "page": req.page, "size": req.size})


@router.post("/homework/detail")
def child_homework_detail(req: ChildHomeworkRequest, parent: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    from app.routers.homework import _homework_to_dict
    repo = Repo(db)
    child = _homework_child(repo, parent, req.student_id)
    hw = _child_homework(repo, child, req.homework_id)
    data = _homework_to_dict(hw)
    data["my_record"] = _parent_record(repo.get_homework_record(hw.id, child.id))
    return ok({"homework": data})


@router.post("/homework/submit")
async def child_homework_submit(student_id: int = Form(...), homework_id: int = Form(...),
                                text_content: str | None = Form(None), file: UploadFile | None = File(None),
                                parent: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    from app.routers.homework import _submit_homework
    repo = Repo(db)
    child = _homework_child(repo, parent, student_id)
    _child_homework(repo, child, homework_id)
    return await _submit_homework(homework_id, text_content, file, child, db, parent)


@router.post("/homework/download")
def child_homework_download(req: ChildHomeworkRequest, parent: User = Depends(get_verified_user), db: Session = Depends(get_db)):
    from app.services.document_service import render_text_to_pdf
    repo = Repo(db)
    child = _homework_child(repo, parent, req.student_id)
    hw = _child_homework(repo, child, req.homework_id)
    record = repo.get_homework_record(hw.id, child.id)
    text = f"作业描述：\n{hw.description or '无'}\n\n学生作答：\n{record.text_content if record and record.text_content else '无'}"
    if record and record.review_score is not None:
        text += f"\n\n批改分数：{record.review_score}\n评语：{record.review_comment or '无'}"
    data = render_text_to_pdf(hw.title, text)
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="homework-{hw.id}.pdf"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


# ---------------- 接口 ----------------


@router.post("/bind")
def bind_child(
    req: BindRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """家长凭学生绑定码绑定孩子（PRD 5.7）。一个家长可绑多个。"""
    _require_parent(parent)

    repo = Repo(db)
    child = repo.get_student_by_code_for_update(req.bind_code)
    if not child:
        raise _not_found("绑定码不存在或已失效")

    if repo.get_parent_student_for_update(parent.id, child.id):
        raise _bad_request("已绑定该学生")

    try:
        repo.add_parent_student(ParentStudent(parent_id=parent.id, student_id=child.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, 'args', [None])[0] != 1062 and 'UNIQUE constraint failed' not in str(exc.orig):
            raise
        raise _bad_request("已绑定该学生") from exc

    return ok({
        "student_id": child.id,
        "username": child.username,
        "nickname": child.nickname,
        "total_points": child.total_points,
    })


@router.post("/children")
async def my_children(
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """我绑定的孩子列表（PRD 5.7）。无入参。"""
    _require_parent(parent)

    children = Repo(db).list_children(parent.id)
    return ok({
        "list": [
            {
                "student_id": c.id,
                "username": c.username,
                "nickname": c.nickname,
                "avatar": c.avatar,
                "class_id": c.class_id,
                "total_points": c.total_points,
            }
            for c in children
        ],
        "total": len(children),
    })


@router.post("/child-rank")
async def child_rank(
    req: ChildRankRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """查看与学生排行榜一致的榜单及已绑定孩子的排名。"""
    _require_parent(parent)
    repo = Repo(db)
    child = _own_child(repo, parent, req.student_id)
    if child.role != ROLE_STUDENT:
        raise _forbidden("绑定用户不是学生")
    result = rank_response(repo, req, child.id)
    # 家长只需要展示昵称和积分，不返回其他学生用作账号的手机号。
    for item in result["data"]["list"]:
        item["username"] = None
    return result


@router.post("/child-points")
async def child_points(
    req: ChildPointsRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """查看孩子的积分明细（PRD 5.7）。"""
    _require_parent(parent)

    repo = Repo(db)
    child = _own_child(repo, parent, req.student_id)

    logs, total = point_service.list_logs(db, child.id, None, req.page, req.size)
    summary = point_service.summary(db, child.id)

    return ok({
        "student": {
            "id": child.id,
            "username": child.username,
            "nickname": child.nickname,
            "total_points": child.total_points,
        },
        "summary": summary,
        "list": [
            {
                "id": log.id,
                "type": log.type,
                "points": log.points,
                "remark": log.remark,
                "log_date": log.log_date.isoformat() if log.log_date else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/consume")
def consume_points(
    req: ConsumeRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """积分消耗（PRD 5.7）。

    - 校验余额 ≥ 扣分，否则 400
    - 写 PointLog（type=consume，points 为负，operator=家长）
    """
    _require_parent(parent)

    repo = Repo(db)
    child = repo.get_user_by_id_for_update(req.student_id)
    if not child:
        raise _not_found("学生不存在")
    if not repo.get_parent_student_for_update(parent.id, req.student_id):
        raise _forbidden("只能操作自己绑定的孩子")

    try:
        remaining = point_service.consume(
            db,
            child.id,
            req.points,
            remark=f"{req.item}" + (f"：{req.remark}" if req.remark else ""),
            operator_id=parent.id,
        )
    except point_service.PointError as exc:
        db.rollback()
        raise _bad_request(exc.message) from exc

    db.commit()
    return ok({
        "student_id": child.id,
        "item": req.item,
        "points": -req.points,
        "total_points": remaining,
    })


@router.post("/reward")
def reward_points(
    req: RewardRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """为已绑定的孩子按指定数额奖励积分。"""
    _require_parent(parent)
    remark = req.item + (f"：{req.remark}" if req.remark else "")
    if len(remark) > 255:
        raise _bad_request("事项和备注合计不能超过 255 个字符")

    repo = Repo(db)
    child = repo.get_user_by_id_for_update(req.student_id)
    if not child:
        raise _not_found("学生不存在")
    if not repo.get_parent_student_for_update(parent.id, req.student_id):
        raise _forbidden("只能操作自己绑定的孩子")

    try:
        point_service.award_amount(
            db, child.id, req.points, type_=POINT_TYPE_PARENT_REWARD,
            remark=remark, operator_id=parent.id,
        )
    except point_service.PointError as exc:
        db.rollback()
        raise _bad_request(exc.message) from exc

    db.commit()
    return ok({
        "student_id": child.id,
        "item": req.item,
        "points": req.points,
        "total_points": child.total_points,
    })


@router.post("/reward-items")
async def reward_items(parent: User = Depends(get_verified_user)):
    """预设奖励事项。"""
    _require_parent(parent)
    return ok({"list": REWARD_ITEMS})


@router.post("/consume-items")
async def consume_items(parent: User = Depends(get_verified_user)):
    """预设消耗事项（PRD 5.7）。无入参。"""
    _require_parent(parent)
    return ok({"list": CONSUME_ITEMS})


@router.post("/unbind")
def unbind_child(
    req: UnbindRequest,
    parent: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """解除绑定（PRD 5.7）。"""
    _require_parent(parent)

    repo = Repo(db)
    child = repo.get_user_by_id_for_update(req.student_id)
    if not child:
        raise _bad_request("未绑定该学生")
    rel = repo.get_parent_student_for_update(parent.id, req.student_id)
    if not rel:
        raise _bad_request("未绑定该学生")

    db.delete(rel)
    db.commit()

    return ok({"unbound_student_id": req.student_id})