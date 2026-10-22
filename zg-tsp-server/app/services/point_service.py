"""积分发放服务（PRD 6）。

通用规则：
- 积分变动必写 `point_logs`，同步 `users.total_points`
- 日上限服务端强校验
- `total_points` 不为负
- 规则 `enabled=false` 不发放
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.models.constants import POINT_TYPE_CONSUME, ROLE_STUDENT
from app.models.entities import PointLog, User


class PointError(Exception):
    """积分业务异常。由 router 转成 400。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def today() -> date:
    return date.today()


def count_awards_on(db: Session, student_id: int, type_: str, day: date) -> int:
    """某学生某**类型**在某天的发放次数（用于日上限校验）。

    按 `point_logs.type` 统计，而非 rule_key —— PRD 4.1 的 point_logs 表
    没有 rule_key 列，只有 type（checkin/homework/reading/game/consume）。

    重要：`point_rules.daily_limit` 的语义是「每天最多 N 次」（PRD 6 总表
    写的是「1 次」），而**不是**积分上限。
    例如 checkin_daily = {points: 5, daily_limit: 1} 表示
    「每天签到 1 次，每次给 5 分」，而非「每天最多得 1 分」。
    """
    return db.scalar(
        select(func.count(PointLog.id)).where(
            PointLog.student_id == student_id,
            PointLog.type == type_,
            PointLog.log_date == day,
        )
    ) or 0


def sum_points_by_type_on(db: Session, student_id: int, type_: str, day: date) -> int:
    """某学生某类型在某天已获得的积分合计（如游戏当日合计，用于封顶）。"""
    total = db.scalar(
        select(func.coalesce(func.sum(PointLog.points), 0)).where(
            PointLog.student_id == student_id,
            PointLog.type == type_,
            PointLog.log_date == day,
            PointLog.points > 0,
        )
    )
    return total or 0


def award(
    db: Session,
    student_id: int,
    type_: str,
    rule_key: str,
    remark: str | None = None,
    operator_id: int | None = None,
    enforce_limit: bool = True,
) -> int:
    """按规则发放积分。

    返回实际发放的积分值；规则禁用或已达日上限时返回 0（不写流水）。
    抛 PointError 表示业务异常（余额不足等）。

    日上限语义（PRD 6）：`daily_limit` 是「每天最多 N 次」，不是积分天花板。
    因此命中次数上限时直接返回 0，**不做部分发放**。
    """
    from app.services.point_rule_service import rule_service

    rule = rule_service.get(db, rule_key)
    # 规则不存在或已禁用 —— 不发放（PRD 6）
    if rule is None or not rule.enabled:
        return 0

    user = Repo(db).get_user_by_id(student_id)
    if user is None or user.role != ROLE_STUDENT:
        raise PointError("仅可为学生账号发放积分")

    points = rule.points
    if points <= 0:
        return 0

    # 日次数上限强校验（PRD 6）
    if enforce_limit and rule.daily_limit is not None:
        times = count_awards_on(db, student_id, type_, today())
        if times + 1 > rule.daily_limit:
            return 0

    db.add(
        PointLog(
            student_id=student_id,
            type=type_,
            points=points,
            remark=remark,
            operator_id=operator_id,
            log_date=today(),
        )
    )
    user.total_points += points
    db.flush()
    return points


def award_game(
    db: Session,
    student_id: int,
    rule_key: str,
    remark: str | None = None,
    operator_id: int | None = None,
) -> int:
    """游戏积分发放：受「每日游戏总积分上限」约束（PRD 5.6 防沉迷）。

    PRD 6 总表注明游戏规则「游戏合计 20」—— 这是**跨规则的积分总和上限**
    （数独三种难度 + 成语接龙共用），与 `daily_limit` 的次数语义不同。
    超出时按剩余额度部分发放。
    """
    from app.models.constants import POINT_TYPE_GAME
    from app.services.point_rule_service import rule_service

    rule = rule_service.get(db, rule_key)
    if rule is None or not rule.enabled or rule.points <= 0:
        return 0

    user = Repo(db).get_user_by_id(student_id)
    if user is None or user.role != ROLE_STUDENT:
        raise PointError("仅可为学生账号发放积分")

    points = rule.points
    daily_cap = rule.daily_limit or 0
    if daily_cap > 0:
        # 所有游戏规则的流水都记 type=game，因此一次统计即可覆盖
        # 数独三种难度 + 成语接龙（PRD 5.6 防沉迷）
        gained_today = sum_points_by_type_on(db, student_id, POINT_TYPE_GAME, today())
        if gained_today + points > daily_cap:
            remaining = daily_cap - gained_today
            if remaining <= 0:
                return 0
            points = remaining

    db.add(
        PointLog(
            student_id=student_id,
            type=POINT_TYPE_GAME,
            points=points,
            remark=remark,
            operator_id=operator_id,
            log_date=today(),
        )
    )
    user.total_points += points
    db.flush()
    return points


def consume(
    db: Session,
    student_id: int,
    points: int,
    remark: str | None = None,
    operator_id: int | None = None,
) -> int:
    """家长扣分（PRD 5.7）。

    校验余额 ≥ 扣分，否则报错；`total_points` 不为负。
    不走规则表（PRD 6：家长扣分不走规则表）。
    """
    if points <= 0:
        raise PointError("扣分数值必须大于 0")

    user = Repo(db).get_user_by_id(student_id)
    if user is None or user.role != ROLE_STUDENT:
        raise PointError("仅可为学生账号扣减积分")

    if user.total_points < points:
        raise PointError(
            f"积分余额不足：当前 {user.total_points} 分，需扣 {points} 分"
        )

    db.add(
        PointLog(
            student_id=student_id,
            type=POINT_TYPE_CONSUME,
            points=-points,  # 流水记负数
            remark=remark,
            operator_id=operator_id,
            log_date=today(),
        )
    )
    user.total_points -= points
    db.flush()
    return user.total_points


def list_logs(
    db: Session,
    student_id: int,
    type_: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[PointLog], int]:
    """积分明细（PRD 5.4）。返回 (当前页, 总数)。"""
    stmt = select(PointLog).where(PointLog.student_id == student_id)
    count_stmt = select(func.count()).select_from(PointLog).where(
        PointLog.student_id == student_id
    )
    if type_:
        stmt = stmt.where(PointLog.type == type_)
        count_stmt = count_stmt.where(PointLog.type == type_)

    total = db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(PointLog.log_date.desc(), PointLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(db.scalars(stmt)), total


def summary(db: Session, student_id: int) -> dict:
    """学生积分概览：今日获得、累计获得、累计消费、当前余额。"""
    user = Repo(db).get_user_by_id(student_id)
    day = today()

    gained_today = db.scalar(
        select(func.coalesce(func.sum(PointLog.points), 0)).where(
            PointLog.student_id == student_id,
            PointLog.log_date == day,
            PointLog.points > 0,
        )
    ) or 0

    total_gained = db.scalar(
        select(func.coalesce(func.sum(PointLog.points), 0)).where(
            PointLog.student_id == student_id,
            PointLog.points > 0,
        )
    ) or 0

    total_consumed = db.scalar(
        select(func.coalesce(func.sum(PointLog.points), 0)).where(
            PointLog.student_id == student_id,
            PointLog.points < 0,
        )
    ) or 0

    return {
        "total_points": user.total_points if user else 0,
        "gained_today": gained_today,
        "total_gained": total_gained,
        "total_consumed": abs(total_consumed),
    }