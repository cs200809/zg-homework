"""P1.6 积分规则管理与积分发放测试（PRD 5.8.3、第 6 节）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

import pytest

from app.db.repo import Repo
from app.models.constants import (
    POINT_TYPE_CHECKIN,
    POINT_TYPE_CONSUME,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.services import point_service
from app.services.point_rule_service import rule_service


def admin_post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


@pytest.fixture(autouse=True)
def _clear_cache():
    """每个用例前后清空规则缓存，避免用例间互相影响。"""
    rule_service.invalidate()
    yield
    rule_service.invalidate()


@pytest.fixture
def set_rule(client, admin_token, db):
    """显式设置规则值，避免依赖被其他用例改动过的种子数据。

    「只增不删」下规则表是共享状态，用例必须自备前置条件。
    更新走 HTTP（另一个 Session），因此返回前先结束 db 的快照事务，
    确保后续 point_service 用 db 读到的是新值。
    """

    def _set(rule_key: str, **fields) -> dict:
        r = admin_post(
            client, "/admin/rules/update", {"rule_key": rule_key, **fields}, token=admin_token
        )
        assert r.status_code == 200, r.text
        db.rollback()  # 结束快照事务，让下次查询取新值
        db.expire_all()
        rule_service.invalidate(rule_key)  # 保险：确保规则缓存不残留
        return r.json()["data"]["rule"]

    return _set


@pytest.fixture
def student(db, make_user):
    """带初始积分的学生。"""
    user, _ = make_user(ROLE_STUDENT, "ps", total_points=0)
    return user


# ==================== 5.8.3 规则列表与详情 ====================


def test_rules_list(client, admin_token):
    """查看全部规则（PRD 5.8.3）。"""
    r = admin_post(client, "/admin/rules/list", token=admin_token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 10  # PRD 4.2 种子
    keys = {i["rule_key"] for i in data["list"]}
    assert {
        "checkin_daily", "checkin_streak_7", "homework_on_time", "homework_late",
        "reading_per_minute", "reading_finish",
        "game_sudoku_easy", "game_sudoku_medium", "game_sudoku_hard", "game_idiom",
    } == keys


def test_rules_list_requires_admin(client, make_user, login):
    token = login(*make_user(ROLE_TEACHER, "rt"))
    assert admin_post(client, "/admin/rules/list", token=token).status_code == 403


def test_rule_detail(client, admin_token, set_rule):
    set_rule("checkin_daily", points=5, daily_limit=1)
    r = admin_post(client, "/admin/rules/detail", {"rule_key": "checkin_daily"}, token=admin_token)
    assert r.status_code == 200
    rule = r.json()["data"]["rule"]
    assert rule["rule_key"] == "checkin_daily"
    assert rule["points"] == 5
    assert rule["daily_limit"] == 1


def test_rule_detail_not_found(client, admin_token):
    r = admin_post(client, "/admin/rules/detail", {"rule_key": "nope"}, token=admin_token)
    assert r.status_code == 404


# ==================== 5.8.3 规则修改 ====================


def test_rule_update_points(client, admin_token, db, refresh):
    """修改积分值（PRD 5.8.3）。"""
    r = admin_post(
        client,
        "/admin/rules/update",
        {"rule_key": "checkin_daily", "points": 99},
        token=admin_token,
    )
    assert r.status_code == 200
    assert r.json()["data"]["rule"]["points"] == 99

    refresh()
    assert Repo(db).get_rule_by_key("checkin_daily").points == 99


def test_rule_update_daily_limit(client, admin_token, db, refresh):
    admin_post(client, "/admin/rules/update", {"rule_key": "game_idiom", "daily_limit": 77}, token=admin_token)
    refresh()
    assert Repo(db).get_rule_by_key("game_idiom").daily_limit == 77


def test_rule_update_extra_config(client, admin_token, db, refresh, set_rule):
    set_rule("reading_per_minute", extra_config='{"single_article_limit": 10}')
    admin_post(
        client,
        "/admin/rules/update",
        {"rule_key": "reading_per_minute", "extra_config": '{"single_article_limit": 25}'},
        token=admin_token,
    )
    refresh()
    import json

    rule = Repo(db).get_rule_by_key("reading_per_minute")
    assert json.loads(rule.extra_config)["single_article_limit"] == 25


def test_rule_update_invalid_json_rejected(client, admin_token):
    r = admin_post(
        client,
        "/admin/rules/update",
        {"rule_key": "checkin_daily", "extra_config": "{not json"},
        token=admin_token,
    )
    assert r.status_code == 400
    assert "合法 JSON" in r.json()["message"]


def test_rule_update_not_found(client, admin_token):
    r = admin_post(client, "/admin/rules/update", {"rule_key": "nope", "points": 1}, token=admin_token)
    assert r.status_code == 404


def test_rule_update_negative_points_rejected(client, admin_token):
    r = admin_post(client, "/admin/rules/update", {"rule_key": "checkin_daily", "points": -5}, token=admin_token)
    assert r.status_code == 400


def test_rule_key_not_updatable(client, admin_token, db, refresh):
    """rule_key 不可改（PRD 5.8.3）—— 传不存在的 key 只会 404，不会新建。"""
    before = len(Repo(db).list_point_rules())
    r = admin_post(
        client,
        "/admin/rules/update",
        {"rule_key": "brand_new_key", "points": 10},
        token=admin_token,
    )
    assert r.status_code == 404
    refresh()
    assert len(Repo(db).list_point_rules()) == before  # 未新增规则


def test_rule_update_writes_admin_log(client, admin_token, db, refresh):
    """修改规则写审计日志（PRD 5.8.3）。"""
    admin = Repo(db).get_user_by_username("admin")
    admin_post(client, "/admin/rules/update", {"rule_key": "checkin_daily", "points": 42}, token=admin_token)
    refresh()

    from sqlalchemy import select

    from app.models.entities import AdminLog

    logs = db.scalars(
        select(AdminLog).where(AdminLog.admin_id == admin.id, AdminLog.action == "rule_update")
    ).all()
    assert len(logs) >= 1
    assert "checkin_daily" in logs[-1].detail


# ==================== 批量更新 ====================


def test_rule_batch_update(client, admin_token, db, refresh):
    r = admin_post(
        client,
        "/admin/rules/batch-update",
        {"rules": [
            {"rule_key": "game_sudoku_easy", "points": 6},
            {"rule_key": "game_sudoku_medium", "points": 11},
        ]},
        token=admin_token,
    )
    assert r.status_code == 200
    assert r.json()["data"]["count"] == 2

    refresh()
    assert Repo(db).get_rule_by_key("game_sudoku_easy").points == 6
    assert Repo(db).get_rule_by_key("game_sudoku_medium").points == 11


def test_rule_batch_update_unknown_key_rolls_back(client, admin_token, db, refresh):
    """任一条目非法则整批拒绝（PRD 5.8.3 事务一致性）。"""
    before = Repo(db).get_rule_by_key("game_sudoku_easy").points

    r = admin_post(
        client,
        "/admin/rules/batch-update",
        {"rules": [
            {"rule_key": "game_sudoku_easy", "points": 100},
            {"rule_key": "not_exist", "points": 1},
        ]},
        token=admin_token,
    )
    assert r.status_code == 404

    refresh()
    # 第一条不应被写入
    assert Repo(db).get_rule_by_key("game_sudoku_easy").points == before


def test_rule_batch_update_duplicate_key_rejected(client, admin_token):
    r = admin_post(
        client,
        "/admin/rules/batch-update",
        {"rules": [
            {"rule_key": "game_idiom", "points": 1},
            {"rule_key": "game_idiom", "points": 2},
        ]},
        token=admin_token,
    )
    assert r.status_code == 400
    assert "重复" in r.json()["message"]


def test_rule_batch_update_empty_rejected(client, admin_token):
    r = admin_post(client, "/admin/rules/batch-update", {"rules": []}, token=admin_token)
    assert r.status_code == 400


# ==================== 第 6 节：积分发放语义 ====================


def test_award_uses_rule_points(db, student, set_rule, refresh):
    """发放积分读规则值（PRD 6）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    got = point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")
    assert got == 5
    assert student.total_points == 5


def test_award_writes_point_log(db, student, set_rule, refresh):
    """积分变动必写 point_logs（PRD 6）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily", remark="每日签到")
    db.commit()
    refresh()

    logs, total = point_service.list_logs(db, student.id)
    assert total == 1
    assert logs[0].points == 5
    assert logs[0].remark == "每日签到"


def test_disabled_rule_gives_nothing(db, student, set_rule, refresh):
    """规则 enabled=false 不发放（PRD 6、第 12 节验收）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=False)
    refresh()

    got = point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")
    assert got == 0
    assert student.total_points == 0
    # 且不应写流水
    _, total = point_service.list_logs(db, student.id)
    assert total == 0


def test_updated_rule_takes_effect_immediately(db, student, set_rule, client, admin_token, refresh):
    """admin 改积分后，新发放立即按新值执行（PRD 5.8.3、第 12 节验收）。

    这是缓存失效的核心验收点：改完不重启服务、不手动清缓存，下一次发放就用新值。
    """
    set_rule("checkin_daily", points=5, daily_limit=100, enabled=True)
    refresh()
    # 先读一次让服务端规则缓存热起来
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 5

    # 通过 HTTP 改规则（服务端会失效自己的缓存）
    admin_post(client, "/admin/rules/update", {"rule_key": "checkin_daily", "points": 50}, token=admin_token)

    # 不手动清缓存、不重启；refresh 只让测试自己的 db 会话读到新值
    refresh()
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 50


def test_rule_cache_invalidated_without_restart(db, set_rule, refresh):
    """直接验证规则服务缓存失效：改动后 get() 必须返回新值。"""
    set_rule("game_sudoku_easy", points=5)
    refresh()
    assert rule_service.get(db, "game_sudoku_easy").points == 5  # 缓存热

    set_rule("game_sudoku_easy", points=9)
    refresh()
    # set_rule 内部会失效缓存；这里确认服务确实不返回旧值
    assert rule_service.get(db, "game_sudoku_easy").points == 9


def test_daily_limit_enforced(db, student, set_rule, refresh):
    """日上限服务端强校验（PRD 6、第 12 节验收）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 5
    # 第二次已达上限，不再发放
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 0
    assert student.total_points == 5


def test_daily_limit_counts_times_not_points(db, student, set_rule, refresh):
    """daily_limit 是「每天 N 次」而非积分上限（PRD 6）。

    checkin_daily = {points: 5, daily_limit: 1} 应表示「每天 1 次、每次 5 分」，
    而不是「每天最多得 1 分」。
    """
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()

    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 5
    # 次数已满 → 直接 0，不做部分发放
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 0
    assert student.total_points == 5


def test_daily_limit_three_times(db, student, set_rule, refresh):
    """上限 3 次则可发 3 次。"""
    set_rule("checkin_daily", points=5, daily_limit=3, enabled=True)
    refresh()

    for i in range(3):
        assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 5
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 0
    assert student.total_points == 15


def test_daily_limit_zero_blocks_all(db, student, set_rule, refresh):
    """daily_limit=0 表示当天不允许发放。"""
    set_rule("checkin_daily", points=5, daily_limit=0, enabled=True)
    refresh()

    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily") == 0
    assert student.total_points == 0


def test_award_unknown_rule_gives_nothing(db, student, set_rule, refresh):
    set_rule("checkin_daily", points=5, enabled=True)
    refresh()
    assert point_service.award(db, student.id, POINT_TYPE_CHECKIN, "no_such_rule") == 0


def test_award_non_student_rejected(db, make_user, set_rule, refresh):
    set_rule("checkin_daily", points=5, enabled=True)
    refresh()
    teacher, _ = make_user(ROLE_TEACHER, "pt")
    with pytest.raises(point_service.PointError):
        point_service.award(db, teacher.id, POINT_TYPE_CHECKIN, "checkin_daily")


# ==================== 第 6 节：家长扣分 ====================


def test_consume_success(db, student, make_user, set_rule, refresh):
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")
    db.commit()
    refresh()

    parent, _ = make_user("parent", "pc")
    point_service.consume(db, student.id, 3, remark="看手机", operator_id=parent.id)
    db.commit()
    refresh()

    assert student.total_points == 2
    logs, total = point_service.list_logs(db, student.id)
    assert total == 2
    # 流水记负数
    consume_log = [l for l in logs if l.type == POINT_TYPE_CONSUME][0]
    assert consume_log.points == -3


def test_consume_insufficient_balance(db, student, refresh):
    """余额不足拦截（PRD 5.7、第 12 节验收）。"""
    refresh()
    with pytest.raises(point_service.PointError) as exc:
        point_service.consume(db, student.id, 100)
    assert "余额不足" in exc.value.message


def test_total_points_never_negative(db, student, set_rule, refresh):
    """total_points 不为负（PRD 6）。"""
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")  # +5
    db.commit()
    refresh()
    point_service.consume(db, student.id, 5)  # -5 → 0
    db.commit()
    refresh()
    assert student.total_points == 0

    with pytest.raises(point_service.PointError):
        point_service.consume(db, student.id, 1)  # 再扣应失败
    refresh()
    assert student.total_points == 0


def test_consume_non_positive_rejected(db, student, refresh):
    refresh()
    for bad in (0, -5):
        with pytest.raises(point_service.PointError):
            point_service.consume(db, student.id, bad)


def test_consume_non_student_rejected(db, make_user, refresh):
    refresh()
    teacher, _ = make_user(ROLE_TEACHER, "pt")
    with pytest.raises(point_service.PointError):
        point_service.consume(db, teacher.id, 1)


# ==================== 概览与明细 ====================


def test_summary(db, student, set_rule, refresh):
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")
    db.commit()
    refresh()
    point_service.consume(db, student.id, 2)
    db.commit()
    refresh()

    s = point_service.summary(db, student.id)
    assert s["total_points"] == 3
    assert s["gained_today"] == 5
    assert s["total_gained"] == 5
    assert s["total_consumed"] == 2


def test_list_logs_filter_by_type(db, student, set_rule, refresh):
    set_rule("checkin_daily", points=5, daily_limit=1, enabled=True)
    refresh()
    point_service.award(db, student.id, POINT_TYPE_CHECKIN, "checkin_daily")
    db.commit()
    refresh()
    point_service.consume(db, student.id, 1)
    db.commit()
    refresh()

    logs, total = point_service.list_logs(db, student.id, type_=POINT_TYPE_CONSUME)
    assert total == 1
    assert logs[0].type == POINT_TYPE_CONSUME

# ==================== 第 6 节：游戏合计上限（PRD 5.6 防沉迷） ====================


def test_game_cap_shared_across_rules(db, student, set_rule, refresh):
    """游戏积分受「每日合计」约束，跨规则累计（PRD 5.6、第 6 节）。"""
    set_rule("game_sudoku_easy", points=5, daily_limit=20, enabled=True)
    set_rule("game_sudoku_medium", points=10, daily_limit=20, enabled=True)
    set_rule("game_idiom", points=1, daily_limit=20, enabled=True)
    refresh()

    # 数独简单 3 次 = 15 分
    for _ in range(3):
        assert point_service.award_game(db, student.id, "game_sudoku_easy") == 5
    # 再发数独中等（10 分）：15 + 10 = 25 > 20 → 只给剩余 5 分
    assert point_service.award_game(db, student.id, "game_sudoku_medium") == 5
    assert student.total_points == 20

    # 已达上限，其余游戏规则不再发放
    assert point_service.award_game(db, student.id, "game_idiom") == 0
    assert student.total_points == 20


def test_game_cap_exactly_reached(db, student, set_rule, refresh):
    """恰好用满上限后不再发放。"""
    set_rule("game_sudoku_easy", points=20, daily_limit=20, enabled=True)
    refresh()

    assert point_service.award_game(db, student.id, "game_sudoku_easy") == 20
    assert point_service.award_game(db, student.id, "game_sudoku_easy") == 0


def test_game_logs_record_type_game(db, student, set_rule, refresh):
    """游戏流水统一记 type=game（PRD 4.1）。"""
    from sqlalchemy import select

    from app.models.entities import PointLog
    from app.models.constants import POINT_TYPE_GAME

    set_rule("game_sudoku_hard", points=15, daily_limit=20, enabled=True)
    refresh()
    point_service.award_game(db, student.id, "game_sudoku_hard")
    db.commit()
    refresh()

    rows = db.scalars(
        select(PointLog).where(
            PointLog.student_id == student.id,
            PointLog.type == POINT_TYPE_GAME,
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].points == 15


def test_game_disabled_rule_gives_nothing(db, student, set_rule, refresh):
    set_rule("game_idiom", points=1, daily_limit=20, enabled=False)
    refresh()
    assert point_service.award_game(db, student.id, "game_idiom") == 0


def test_game_non_student_rejected(db, make_user, set_rule, refresh):
    set_rule("game_idiom", points=1, daily_limit=20, enabled=True)
    refresh()
    teacher, _ = make_user(ROLE_TEACHER, "pg")
    with pytest.raises(point_service.PointError):
        point_service.award_game(db, teacher.id, "game_idiom")
