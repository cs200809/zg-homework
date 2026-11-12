"""积分接口（PRD 5.4）。

排行榜：
- 今日榜：按当日 PointLog 聚合，前 50
- 总榜：按 total_points，前 50
- 同分按达成时间先后
- 返回 `my_rank`（不在前 50 也可见自己排名）
- **排除 admin 角色**
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import (
    POINT_TYPE_CHECKIN,
    POINT_TYPE_CONSUME,
    POINT_TYPE_GAME,
    POINT_TYPE_HOMEWORK,
    POINT_TYPE_PARENT_REWARD,
    POINT_TYPE_READING,
    POINT_TYPE_REVIEW,
    ROLE_PARENT,
    ROLE_STUDENT,
)
from app.models.entities import User
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, ok
from app.services import point_service

router = APIRouter(prefix="/points", tags=["积分"])

# 榜单最多展示条数（PRD 5.4）
MAX_RANK_SIZE = 50

POINT_TYPES = (
    POINT_TYPE_CHECKIN,
    POINT_TYPE_HOMEWORK,
    POINT_TYPE_PARENT_REWARD,
    POINT_TYPE_READING,
    POINT_TYPE_GAME,
    POINT_TYPE_CONSUME,
    POINT_TYPE_REVIEW,
)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


# ---------------- 出入参 ----------------


class RankRequest(BaseModel):
    type: str = "day"
    page: int = Field(1, ge=1)
    size: int = Field(MAX_RANK_SIZE, ge=1, le=MAX_RANK_SIZE)

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in ("day", "total"):
            raise ValueError('type 必须是 "day" 或 "total"')
        return v


class PointLogRequest(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)
    type: str | None = None

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str | None) -> str | None:
        if v is not None and v not in POINT_TYPES:
            raise ValueError(f"type 必须是 {', '.join(POINT_TYPES)} 之一")
        return v


# ---------------- 接口 ----------------


@router.post("/rank")
async def rank(
    req: RankRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """排行榜（PRD 5.4、8）。

    权限：admin/teacher/student 只读；**parent 无权限**（PRD 8 权限矩阵）。
    榜单排除 admin 角色（PRD 5.4、第 8 节）。
    """
    if user.role == ROLE_PARENT:
        raise _forbidden("家长无排行榜查看权限")

    student_id = user.id if user.role == ROLE_STUDENT else None
    return rank_response(Repo(db), req, student_id)


def rank_response(repo: Repo, req: RankRequest, student_id: int | None):
    """构造排行榜响应；student_id 为需要查询名次的学生，None 表示无个人排名。"""
    size = min(req.size, MAX_RANK_SIZE)

    if req.type == "day":
        day = date.today()
        rows, total = repo.rank_day(day, req.page, size)
        my_rank = repo.rank_position(student_id, day) if student_id is not None else 0
    else:
        rows, total = repo.rank_total(req.page, size)
        my_rank = repo.rank_position(student_id, None) if student_id is not None else 0

    # 补齐昵称
    result = []
    for idx, (sid, pts) in enumerate(rows):
        u = repo.get_user_by_id(sid)
        result.append({
            "rank": (req.page - 1) * size + idx + 1,
            "user_id": sid,
            "username": u.username if u else None,
            "nickname": (u.nickname if u else None),
            "points": pts,
        })

    return ok({
        "type": req.type,
        "list": result,
        "total": total,
        "page": req.page,
        "size": size,
        # 不在前 50 也可见自己的排名（PRD 5.4）
        "my_rank": my_rank,
    })


@router.post("/log")
async def point_log(
    req: PointLogRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """积分明细（PRD 5.4）。仅学生可见自己的。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可查看积分明细")

    logs, total = point_service.list_logs(db, student.id, req.type, req.page, req.size)
    return ok({
        "list": [
            {
                "id": log.id,
                "type": log.type,
                "points": log.points,
                "remark": log.remark,
                "operator_id": log.operator_id,
                "log_date": log.log_date.isoformat() if log.log_date else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/summary")
async def point_summary(
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """积分概览（PRD 5.4）。仅学生。无入参。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可查看积分概览")

    data = point_service.summary(db, student.id)
    today = date.today()
    data["gained_today_rank"] = (
        Repo(db).rank_position(student.id, today) if student.total_points > 0 else 0
    )
    return ok(data)