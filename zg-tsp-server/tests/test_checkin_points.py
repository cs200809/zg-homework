"""P3 签到与排行榜测试（PRD 5.4）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

from datetime import date, timedelta

import pytest

from app.db.repo import Repo
from app.models.constants import (
    POINT_TYPE_CHECKIN,
    POINT_TYPE_CONSUME,
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import Checkin, PointLog
from app.services.point_rule_service import rule_service


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


@pytest.fixture(autouse=True)
def _clear_cache():
    rule_service.invalidate()
    yield
    rule_service.invalidate()


@pytest.fixture
def set_rule(client, admin_token, db):
    def _set(rule_key: str, **fields) -> None:
        r = post(client, "/admin/rules/update", {"rule_key": rule_key, **fields}, token=admin_token)
        assert r.status_code == 200, r.text
        db.rollback()
        db.expire_all()
        rule_service.invalidate(rule_key)

    return _set


# ==================== 签到 ====================


def test_checkin_gives_points(client, login, make_user, set_rule, refresh, db):
    """签到 +5（PRD 5.4、4.2）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    student, pw = make_user(ROLE_STUDENT, "ci")

    r = post(client, "/checkin/do", token=login(student, pw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["already_checked"] is False
    assert data["points"] == 5
    assert data["streak"] == 1

    refresh()
    assert student.total_points == 5


def test_checkin_twice_same_day(client, login, make_user, set_rule, refresh, db):
    """当天重复签到不重复发放（PRD 5.4）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    student, pw = make_user(ROLE_STUDENT, "ci2")
    token = login(student, pw)

    post(client, "/checkin/do", token=token)
    r = post(client, "/checkin/do", token=token)
    assert r.status_code == 200
    assert r.json()["data"]["already_checked"] is True

    refresh()
    assert student.total_points == 5  # 未翻倍


def test_checkin_status_before_and_after(client, login, make_user, set_rule):
    """签到状态查询（PRD 5.4）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    student, pw = make_user(ROLE_STUDENT, "cs")
    token = login(student, pw)

    r = post(client, "/checkin/status", token=token)
    assert r.json()["data"]["checked_in"] is False

    post(client, "/checkin/do", token=token)
    r = post(client, "/checkin/status", token=token)
    data = r.json()["data"]
    assert data["checked_in"] is True
    assert data["points"] == 5
    assert data["streak"] == 1
    assert len(data["recent"]) == 1


def test_checkin_writes_point_log(client, login, make_user, set_rule, refresh, db):
    """签到积分写 point_logs（PRD 6：所有积分变动必写流水）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    student, pw = make_user(ROLE_STUDENT, "ci3")
    post(client, "/checkin/do", token=login(student, pw))
    refresh()

    from sqlalchemy import select

    logs = db.scalars(
        select(PointLog).where(
            PointLog.student_id == student.id,
            PointLog.type == POINT_TYPE_CHECKIN,
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].points == 5


def test_checkin_disabled_rule_gives_nothing(client, login, make_user, set_rule, refresh, db):
    """规则禁用不发放（PRD 6）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=False)
    student, pw = make_user(ROLE_STUDENT, "ci4")

    r = post(client, "/checkin/do", token=login(student, pw))
    assert r.status_code == 200
    assert r.json()["data"]["points"] == 0

    refresh()
    assert student.total_points == 0


def test_checkin_streak_bonus_on_7th_day(client, login, make_user, set_rule, refresh, db):
    """连续 7 天额外 +10（PRD 5.4、第 12 节验收）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    set_rule("checkin_streak_7", points=10, daily_limit=1, enabled=True)

    student, pw = make_user(ROLE_STUDENT, "st7")
    token = login(student, pw)

    # 造历史：前 6 天已签到
    today = date.today()
    for i in range(1, 7):
        db.add(Checkin(
            student_id=student.id,
            checkin_date=today - timedelta(days=i),
            points=5,
            streak=i,
        ))
    db.commit()
    refresh()

    r = post(client, "/checkin/do", token=token)
    data = r.json()["data"]
    assert data["streak"] == 7
    assert data["streak_bonus"] == 10
    assert data["points"] == 5

    refresh()
    assert student.total_points == 5 + 10


def test_checkin_no_bonus_on_6th_day(client, login, make_user, set_rule, refresh, db):
    """第 6 天不发连签奖励。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    set_rule("checkin_streak_7", points=10, daily_limit=1, enabled=True)

    student, pw = make_user(ROLE_STUDENT, "st6")
    today = date.today()
    for i in range(1, 6):
        db.add(Checkin(student_id=student.id, checkin_date=today - timedelta(days=i), points=5, streak=i))
    db.commit()
    refresh()

    r = post(client, "/checkin/do", token=login(student, pw))
    assert r.json()["data"]["streak"] == 6
    assert r.json()["data"]["streak_bonus"] == 0


def test_checkin_broken_streak_restarts(client, login, make_user, set_rule, refresh, db):
    """断签后连续天数归零重算。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    student, pw = make_user(ROLE_STUDENT, "bk")
    today = date.today()
    # 第 3 天前断过（有 5 天前和 1 天前，无 2 天前）
    for i in (5, 1):
        db.add(Checkin(student_id=student.id, checkin_date=today - timedelta(days=i), points=5, streak=i))
    db.commit()
    refresh()

    r = post(client, "/checkin/do", token=login(student, pw))
    assert r.json()["data"]["streak"] == 2  # 昨天 + 今天


def test_teacher_cannot_checkin(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "ct")
    r = post(client, "/checkin/do", token=login(teacher, pw))
    assert r.status_code == 403


def test_parent_cannot_checkin(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "cp")
    assert post(client, "/checkin/do", token=login(parent, pw)).status_code == 403


# ==================== 排行榜 ====================


def _max_student_points(db):
    """当前库中学生最高积分 —— 用于把测试数据顶到榜首，避免落在前 50 之外。"""
    from sqlalchemy import func, select

    from app.models.entities import User

    return db.scalar(
        select(func.coalesce(func.max(User.total_points), 0)).where(User.role == "student")
    ) or 0


def _max_today_points(db):
    """当前库中今日单日最高积分。

    注意不能写 max(sum(...)) —— MySQL 不允许对聚合结果再聚合，
    需先用子查询按学生分组求和，再取最大值。
    """
    from sqlalchemy import func, select

    today = date.today()
    per_student = (
        select(PointLog.student_id.label("sid"), func.sum(PointLog.points).label("pts"))
        .where(PointLog.log_date == today, PointLog.points > 0)
        .group_by(PointLog.student_id)
        .subquery()
    )
    return db.scalar(
        select(func.coalesce(func.max(per_student.c.pts), 0))
    ) or 0


@pytest.fixture
def ranked_students(db, make_user, refresh):
    """造 3 个学生，今日积分递减，稳定进入前 50。

    「只增不删」下库中会持续累积高分学生（历史用例的 90 万分等），
    写死数值会随跑动次数失效，因此动态取当前最高分再往上取三档。
    """
    today = date.today()
    base = max(_max_student_points(db), _max_today_points(db)) + 1000

    students = []
    # 递减：s1 最高、s3 最低，便于断言 rank 递增
    for i, offset in enumerate((3, 2, 1), start=1):
        pts = base + offset
        stu, _ = make_user(ROLE_STUDENT, f"rk{i}")
        stu.total_points = pts
        db.add(PointLog(
            student_id=stu.id,
            type=POINT_TYPE_CHECKIN,
            points=pts,
            log_date=today,
        ))
        db.commit()
        students.append((stu, pts))
    refresh()
    return students


def _rank_map(rows):
    """user_id -> points，便于按自己的学生断言相对顺序。"""
    return {r["user_id"]: r["points"] for r in rows}


def test_rank_day_sorted_desc(client, login, ranked_students):
    """今日榜按当日流水倒序（PRD 5.4）。

    库中会累积其他用例的积分数据，因此断言「本用例三个学生的相对顺序」，
    而非全局前三。
    """
    (s1, p1), (s2, p2), (s3, p3) = ranked_students
    r = post(client, "/points/rank", {"type": "day", "size": 50}, token=login(s1))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["type"] == "day"

    m = _rank_map(data["list"])
    assert m[s1.id] == p1
    assert m[s2.id] == p2
    assert m[s3.id] == p3

    # 名次连续且递减
    rows = {r["user_id"]: r["rank"] for r in data["list"]}
    assert rows[s1.id] < rows[s2.id] < rows[s3.id]

    # 整体按积分倒序
    pts = [u["points"] for u in data["list"]]
    assert pts == sorted(pts, reverse=True)


def test_rank_day_my_rank(client, login, ranked_students):
    """返回 my_rank（PRD 5.4）。库中有历史数据时只断言排在自己三人之前的关系。"""
    (s1, _), (s2, _), _ = ranked_students
    r = post(client, "/points/rank", {"type": "day", "size": 50}, token=login(s2))
    data = r.json()["data"]

    rows = {u["user_id"]: u["rank"] for u in data["list"]}
    assert rows[s2.id] == data["my_rank"]
    assert data["my_rank"] > rows[s1.id]  # 20 分排在 30 分之后


def test_rank_total_uses_total_points(client, login, ranked_students):
    """总榜按 total_points 排序（PRD 5.4）。"""
    (s1, p1), (s2, p2), (s3, p3) = ranked_students
    r = post(client, "/points/rank", {"type": "total", "size": 50}, token=login(s1))
    data = r.json()["data"]
    assert data["type"] == "total"

    m = _rank_map(data["list"])
    assert m[s1.id] == p1
    assert m[s2.id] == p2
    assert m[s3.id] == p3

    rows = {u["user_id"]: u["rank"] for u in data["list"]}
    assert rows[s1.id] < rows[s2.id] < rows[s3.id]


def test_rank_max_50(client, login, ranked_students):
    """前 50（PRD 5.4）。"""
    top_stu, _ = ranked_students[0]
    r = post(client, "/points/rank", {"type": "day", "size": 100}, token=login(top_stu))
    assert r.status_code == 400  # 超过 50 拒绝

    r = post(client, "/points/rank", {"type": "day", "size": 50}, token=login(top_stu))
    assert r.status_code == 200


def test_rank_excludes_admin(client, login, ranked_students, admin_token, db, refresh, make_user):
    """排除 admin 角色（PRD 5.4、第 8 节、第 12 节验收）。

    给 admin 塞极高积分，仍不应出现在榜单中。
    """
    # 用独立的测试 admin 账号，不给真实 admin 塞积分（避免污染开发库）。
    admin, _ = make_user(ROLE_ADMIN, "adm")
    admin.total_points = 99999
    db.add(PointLog(
        student_id=admin.id,
        type=POINT_TYPE_CHECKIN,
        points=99999,
        log_date=date.today(),
    ))
    db.commit()
    refresh()

    top_stu, _ = ranked_students[0]
    for kind in ("day", "total"):
        r = post(client, "/points/rank", {"type": kind, "size": 50}, token=login(top_stu))
        ids = [u["user_id"] for u in r.json()["data"]["list"]]
        assert admin.id not in ids, f"{kind} 榜不应包含 admin"


def test_rank_tie_break_by_earlier(client, login, db, make_user, refresh):
    """同分按达成时间先后（PRD 5.4）：先得分者靠前。

    库中有大量同分的历史数据，因此只看本用例两人的相对名次。
    """
    today = date.today()
    first, _ = make_user(ROLE_STUDENT, "tb1")
    second, _ = make_user(ROLE_STUDENT, "tb2")

    # 动态取当前最高分 +500，确保两人稳定进入前 50
    pts = max(_max_student_points(db), _max_today_points(db)) + 500
    # first 先写流水，second 后写，但分值相同
    db.add(PointLog(student_id=first.id, type=POINT_TYPE_CHECKIN, points=pts, log_date=today))
    db.commit()
    db.add(PointLog(student_id=second.id, type=POINT_TYPE_CHECKIN, points=pts, log_date=today))
    db.commit()
    refresh()

    r = post(client, "/points/rank", {"type": "day", "size": 50}, token=login(first))
    rows = {u["user_id"]: u["rank"] for u in r.json()["data"]["list"]}
    assert rows[first.id] < rows[second.id]


def test_rank_requires_login(client):
    assert post(client, "/points/rank", {"type": "day"}).status_code == 401


def test_rank_invalid_type(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "rt")
    r = post(client, "/points/rank", {"type": "week"}, token=login(student, pw))
    assert r.status_code == 400


def test_teacher_can_view_rank_readonly(client, login, ranked_students, make_user):
    """老师可只读查看排行榜（PRD 8）。"""
    teacher, pw = make_user(ROLE_TEACHER, "tv")
    r = post(client, "/points/rank", {"type": "day"}, token=login(teacher, pw))
    assert r.status_code == 200
    assert "list" in r.json()["data"]


def test_admin_can_view_rank_readonly(client, ranked_students, admin_token):
    """admin 可只读查看排行榜，但自己不出现（PRD 8）。"""
    r = post(client, "/points/rank", {"type": "total"}, token=admin_token)
    assert r.status_code == 200


def test_parent_cannot_view_rank(client, login, make_user):
    """PRD 8：家长无排行榜权限。"""
    parent, pw = make_user(ROLE_PARENT, "pv")
    r = post(client, "/points/rank", {"type": "day"}, token=login(parent, pw))
    assert r.status_code == 403


# ==================== 积分明细与概览 ====================


def test_point_log_paged(client, login, make_user, db, refresh):
    """积分明细分页（PRD 5.4）。"""
    from app.services import point_service

    student, pw = make_user(ROLE_STUDENT, "pl")
    today = date.today()
    for _ in range(3):
        db.add(PointLog(student_id=student.id, type=POINT_TYPE_CHECKIN, points=5, log_date=today))
    db.commit()
    refresh()

    r = post(client, "/points/log", {"page": 1, "size": 2}, token=login(student, pw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["list"]) == 2
    assert data["total"] == 3
    assert "password_hash" not in str(data)


def test_point_log_filter_by_type(client, login, make_user, db, refresh):
    """按类型筛选（PRD 5.4）。"""
    student, pw = make_user(ROLE_STUDENT, "pf")
    today = date.today()
    db.add(PointLog(student_id=student.id, type=POINT_TYPE_CHECKIN, points=5, log_date=today))
    db.add(PointLog(student_id=student.id, type=POINT_TYPE_CONSUME, points=-3, log_date=today))
    db.commit()
    refresh()

    r = post(client, "/points/log", {"type": POINT_TYPE_CONSUME}, token=login(student, pw))
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["list"][0]["type"] == POINT_TYPE_CONSUME
    assert data["list"][0]["points"] == -3


def test_point_log_invalid_type(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "pi")
    r = post(client, "/points/log", {"type": "bogus"}, token=login(student, pw))
    assert r.status_code == 400


def test_point_log_only_student(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "plo")
    r = post(client, "/points/log", {}, token=login(teacher, pw))
    assert r.status_code == 403


def test_point_summary(client, login, make_user, db, refresh):
    """积分概览（PRD 5.4）。"""
    student, pw = make_user(ROLE_STUDENT, "psm", total_points=0)
    today = date.today()
    db.add(PointLog(student_id=student.id, type=POINT_TYPE_CHECKIN, points=15, log_date=today))
    db.add(PointLog(student_id=student.id, type=POINT_TYPE_CONSUME, points=-5, log_date=today))
    db.commit()
    student.total_points = 10
    db.commit()
    refresh()

    r = post(client, "/points/summary", token=login(student, pw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_points"] == 10
    assert data["gained_today"] == 15
    assert data["total_gained"] == 15
    assert data["total_consumed"] == 5


def test_point_summary_only_student(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "psp")
    r = post(client, "/points/summary", token=login(parent, pw))
    assert r.status_code == 403