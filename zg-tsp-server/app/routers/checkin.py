"""签到接口（PRD 5.4）。

- 每日 1 次 +5（读 checkin_daily 规则）
- 连续 7 天额外 +10（读 checkin_streak_7 规则）
- 当天已签到返回状态，不重复发放
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import POINT_TYPE_CHECKIN, ROLE_STUDENT
from app.models.entities import Checkin, User
from app.utils.deps import get_verified_user
from app.utils.response import CODE_FORBIDDEN, ok

router = APIRouter(prefix="/checkin", tags=["签到"])

# 连续签到奖励所需天数（PRD 4.2：checkin_streak_7）
STREAK_REWARD_DAYS = 7


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _require_student(user: User) -> None:
    if user.role != ROLE_STUDENT:
        raise _forbidden("仅学生可签到")


def _calc_streak(checkins: list[Checkin], today: date) -> int:
    """计算连续签到天数（含今天）。

    从今天往前逐天回溯，遇到断签即停止。
    """
    if not checkins:
        return 0

    dates = {c.checkin_date for c in checkins}
    # 今天没签到时，从昨天开始算（今天还有机会签）
    cursor = today if today in dates else today - timedelta(days=1)

    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.post("/do")
async def do_checkin(
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """学生签到（PRD 5.4）。无入参。"""
    _require_student(student)

    repo = Repo(db)
    today = date.today()

    existing = repo.get_checkin(student.id, today)
    if existing:
        # 当天已签到，不重复发放（PRD 5.4）
        return ok({
            "already_checked": True,
            "checkin_date": today.isoformat(),
            "points": existing.points or 0,
            "streak": existing.streak or 0,
            "total_points": student.total_points,
        })

    from app.services import point_service

    # 先建记录再算连续天数（本次签到也计入）
    checkin = repo.add_checkin(
        Checkin(
            student_id=student.id,
            checkin_date=today,
            points=0,
            streak=0,
        )
    )

    streak = _calc_streak(repo.list_checkins_desc(student.id), today)
    checkin.streak = streak

    # 基础签到积分
    base = point_service.award(
        db,
        student.id,
        POINT_TYPE_CHECKIN,
        "checkin_daily",
        remark="每日签到",
        operator_id=student.id,
    )
    checkin.points = base

    # 连续 7 天额外奖励
    #
    # 注意：这里必须 enforce_limit=False。
    # `daily_limit` 按 point_logs.type 计数，而 checkin_daily 与
    # checkin_streak_7 的 type 都是 checkin —— 若启用次数限制，
    # 基础签到会占满当日唯一额度，导致连签奖励永远发不出去。
    # 连签奖励由 streak % 7 == 0 保证「每满 7 天只发一次」，无需再限次数。
    bonus = 0
    if streak > 0 and streak % STREAK_REWARD_DAYS == 0:
        bonus = point_service.award(
            db,
            student.id,
            POINT_TYPE_CHECKIN,
            "checkin_streak_7",
            remark=f"连续签到 {streak} 天奖励",
            operator_id=student.id,
            enforce_limit=False,
        )

    db.commit()
    db.refresh(student)

    return ok({
        "already_checked": False,
        "checkin_date": today.isoformat(),
        "points": base,
        "streak": streak,
        "streak_bonus": bonus,
        "total_points": student.total_points,
    })


@router.post("/status")
async def checkin_status(
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """查询当天签到状态（PRD 5.4）。无入参。"""
    _require_student(student)

    repo = Repo(db)
    today = date.today()
    checkin = repo.get_checkin(student.id, today)
    checkins = repo.list_checkins_desc(student.id)

    return ok({
        "checked_in": checkin is not None,
        "checkin_date": today.isoformat(),
        "points": checkin.points if checkin else 0,
        "streak": _calc_streak(checkins, today),
        "total_points": student.total_points,
        # 最近 7 天打卡情况，供前端渲染日历
        "recent": [
            {
                "date": c.checkin_date.isoformat(),
                "points": c.points,
                "streak": c.streak,
            }
            for c in checkins[:7]
        ],
    })