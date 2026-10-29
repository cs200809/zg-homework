"""P4 家长端测试（PRD 5.7）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.db.repo import Repo
from app.models.constants import (
    POINT_TYPE_CONSUME,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import PointLog


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


@pytest.fixture
def bind_setup(db, make_user, refresh, uname, uniq):
    """(家长, 密码, 学生1, 学生2) —— 学生带唯一绑定码与初始积分。

    绑定码必须逐用例唯一：「只增不删」下固定码会被历史用例的学生占用，
    导致 get_user_by_bind_code 查到别人家的孩子。
    """
    parent, ppw = make_user(ROLE_PARENT, "par")
    # bind_code 字段为 VARCHAR(8)，需控制在 8 位内
    s1, _ = make_user(ROLE_STUDENT, "ch1", bind_code=uniq("C1").upper()[:8], total_points=100)
    s2, _ = make_user(ROLE_STUDENT, "ch2", bind_code=uniq("C2").upper()[:8], total_points=50)
    refresh()
    return parent, ppw, s1, s2


# ==================== 5.7 绑定 ====================


def test_bind_child(client, login, bind_setup, refresh, db):
    """家长凭绑定码绑定孩子（PRD 5.7、第 12 节验收）。"""
    parent, ppw, s1, _ = bind_setup
    r = post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=login(parent, ppw))
    assert r.status_code == 200
    assert r.json()["data"]["student_id"] == s1.id

    refresh()
    assert Repo(db).get_parent_student(parent.id, s1.id) is not None


def test_bind_multiple_children(client, login, bind_setup, refresh, db):
    """一个家长可绑多个孩子（PRD 5.7）。"""
    parent, ppw, s1, s2 = bind_setup
    token = login(parent, ppw)

    assert post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token).status_code == 200
    assert post(client, "/parent/bind", {"bind_code": s2.bind_code}, token=token).status_code == 200

    refresh()
    assert len(Repo(db).list_children(parent.id)) == 2


def test_bind_duplicate_rejected(client, login, bind_setup):
    """重复绑定同一孩子返回 400。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)

    assert post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token).status_code == 200
    r = post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)
    assert r.status_code == 400
    assert "已绑定" in r.json()["message"]


def test_bind_wrong_code(client, login, bind_setup):
    parent, ppw, _, _ = bind_setup
    r = post(client, "/parent/bind", {"bind_code": "NOPE99"}, token=login(parent, ppw))
    assert r.status_code == 404


def test_bind_non_student_code(client, login, db, make_user):
    """绑定码必须属于学生账号。"""
    teacher, tpw = make_user(ROLE_TEACHER, "bt")
    teacher.bind_code = "TEACHER1"
    db.commit()

    parent, ppw = make_user(ROLE_PARENT, "bp")
    r = post(client, "/parent/bind", {"bind_code": "TEACHER1"}, token=login(parent, ppw))
    assert r.status_code == 404


def test_student_cannot_bind(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "sb")
    r = post(client, "/parent/bind", {"bind_code": "BIND001"}, token=login(student, pw))
    assert r.status_code == 403


# ==================== 5.7 孩子列表 ====================


def test_children_list(client, login, bind_setup):
    parent, ppw, s1, s2 = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)
    post(client, "/parent/bind", {"bind_code": s2.bind_code}, token=token)

    r = post(client, "/parent/children", token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 2
    ids = {c["student_id"] for c in data["list"]}
    assert ids == {s1.id, s2.id}
    assert "password_hash" not in str(data)


def test_children_empty(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "ce")
    r = post(client, "/parent/children", token=login(parent, pw))
    assert r.json()["data"]["list"] == []


def test_children_requires_parent(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "crp")
    r = post(client, "/parent/children", token=login(student, pw))
    assert r.status_code == 403


# ==================== 5.7 孩子积分与明细 ====================


def test_child_points_visible_to_parent(client, login, bind_setup, refresh, db):
    """家长查看孩子积分与明细（PRD 5.7）。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    db.add(PointLog(student_id=s1.id, type="checkin", points=20, log_date=date.today()))
    db.commit()
    refresh()

    r = post(client, "/parent/child-points", {"student_id": s1.id, "page": 1, "size": 20}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["student"]["total_points"] == 100
    assert data["summary"]["total_gained"] == 20
    assert data["total"] == 1


def test_child_points_other_parent_forbidden(client, login, bind_setup, db, make_user):
    """不能查看别人家的孩子（PRD 8）。"""
    parent, ppw, s1, _ = bind_setup
    # parent A 绑了 s1
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=login(parent, ppw))

    # parent B 未绑定 s1
    other_parent, other_pw = make_user(ROLE_PARENT, "other")
    r = post(
        client,
        "/parent/child-points",
        {"student_id": s1.id},
        token=login(other_parent, other_pw),
    )
    assert r.status_code == 403


def test_consume_other_parent_forbidden(client, login, bind_setup, db, make_user, refresh):
    """不能扣别人家孩子的分（PRD 8）。"""
    parent, ppw, s1, _ = bind_setup
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=login(parent, ppw))

    other_parent, other_pw = make_user(ROLE_PARENT, "other")
    r = post(
        client,
        "/parent/consume",
        {"student_id": s1.id, "item": "越权扣分", "points": 5},
        token=login(other_parent, other_pw),
    )
    assert r.status_code == 403

    refresh()
    assert s1.total_points == 100  # 未被扣


def test_child_points_unbound_forbidden(client, login, bind_setup, db, make_user):
    """未绑定的学生不可访问（403）。"""
    parent, ppw, s1, _ = bind_setup
    r = post(
        client,
        "/parent/child-points",
        {"student_id": s1.id},
        token=login(parent, ppw),
    )
    assert r.status_code == 403


def test_child_points_nonexistent(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "cnx")
    r = post(client, "/parent/child-points", {"student_id": 999999999}, token=login(parent, pw))
    assert r.status_code == 404


# ==================== 5.7 积分消耗 ====================


def test_consume_items_list(client, login, make_user):
    """预设消耗事项（PRD 5.7）。"""
    parent, pw = make_user(ROLE_PARENT, "ci")
    r = post(client, "/parent/consume-items", token=login(parent, pw))
    assert r.status_code == 200
    items = {i["key"]: i for i in r.json()["data"]["list"]}
    assert items["phone"]["points"] == 5
    assert items["tv"]["points"] == 5
    assert items["toy"]["points"] == 20
    assert items["snack"]["points"] == 10


def test_consume_success(client, login, bind_setup, refresh, db):
    """扣分成功（PRD 5.7、第 12 节验收）。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    r = post(
        client,
        "/parent/consume",
        {"student_id": s1.id, "item": "看手机", "points": 5},
        token=token,
    )
    assert r.status_code == 200
    assert r.json()["data"]["total_points"] == 95

    refresh()
    assert s1.total_points == 95


def test_consume_writes_negative_log_with_operator(client, login, bind_setup, refresh, db):
    """流水记负数且 operator 为家长（PRD 5.7）。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    post(client, "/parent/consume", {"student_id": s1.id, "item": "买零食", "points": 10}, token=token)
    refresh()

    logs = db.scalars(
        select(PointLog).where(
            PointLog.student_id == s1.id,
            PointLog.type == POINT_TYPE_CONSUME,
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].points == -10          # 负数
    assert logs[0].operator_id == parent.id  # operator 为家长
    assert logs[0].remark == "买零食"


def test_consume_remark_appended(client, login, bind_setup, refresh, db):
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    post(
        client,
        "/parent/consume",
        {"student_id": s1.id, "item": "看手机", "points": 5, "remark": "玩了30分钟"},
        token=token,
    )
    refresh()
    log = db.scalars(
        select(PointLog).where(PointLog.student_id == s1.id, PointLog.type == POINT_TYPE_CONSUME)
    ).first()
    assert log.remark == "看手机：玩了30分钟"


def test_consume_insufficient_balance(client, login, bind_setup, refresh, db):
    """余额不足拦截（PRD 5.7、第 12 节验收）。"""
    parent, ppw, s1, _ = bind_setup  # s1 有 100 分
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    r = post(
        client,
        "/parent/consume",
        {"student_id": s1.id, "item": "买玩具", "points": 500},
        token=token,
    )
    assert r.status_code == 400
    assert "余额不足" in r.json()["message"]

    refresh()
    assert s1.total_points == 100  # 未扣


def test_consume_exactly_balance(client, login, bind_setup, refresh, db):
    """余额恰好够时可扣到 0（PRD 6：total_points 不为负）。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    r = post(client, "/parent/consume", {"student_id": s1.id, "item": "清零", "points": 100}, token=token)
    assert r.status_code == 200
    assert r.json()["data"]["total_points"] == 0

    refresh()
    assert s1.total_points == 0

    # 再扣应失败
    r2 = post(client, "/parent/consume", {"student_id": s1.id, "item": "再扣", "points": 1}, token=token)
    assert r2.status_code == 400


def test_consume_non_positive_rejected(client, login, bind_setup):
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    r = post(client, "/parent/consume", {"student_id": s1.id, "item": "x", "points": 0}, token=token)
    assert r.status_code == 400


def test_consume_unbound_child_forbidden(client, login, bind_setup):
    """不能扣未绑定孩子的分（PRD 8）。"""
    parent, ppw, s1, _ = bind_setup
    r = post(
        client,
        "/parent/consume",
        {"student_id": s1.id, "item": "越权", "points": 5},
        token=login(parent, ppw),
    )
    assert r.status_code == 403


def test_consume_by_teacher_forbidden(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "cf")
    r = post(client, "/parent/consume", {"student_id": 1, "item": "x", "points": 1}, token=login(teacher, pw))
    assert r.status_code == 403


# ==================== 5.7 解绑 ====================


def test_unbind(client, login, bind_setup, refresh, db):
    """解除绑定（PRD 5.7）。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)

    r = post(client, "/parent/unbind", {"student_id": s1.id}, token=token)
    assert r.status_code == 200

    refresh()
    assert Repo(db).get_parent_student(parent.id, s1.id) is None


def test_unbind_not_bound(client, login, bind_setup):
    parent, ppw, s1, _ = bind_setup
    r = post(client, "/parent/unbind", {"student_id": s1.id}, token=login(parent, ppw))
    assert r.status_code == 400


def test_unbind_then_rebind(client, login, bind_setup, refresh, db):
    """解绑后可重新绑定。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)

    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)
    post(client, "/parent/unbind", {"student_id": s1.id}, token=token)

    r = post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)
    assert r.status_code == 200

    refresh()
    assert Repo(db).get_parent_student(parent.id, s1.id) is not None


def test_unbind_keeps_points(client, login, bind_setup, refresh, db):
    """解绑不影响孩子的积分与流水。"""
    parent, ppw, s1, _ = bind_setup
    token = login(parent, ppw)
    post(client, "/parent/bind", {"bind_code": s1.bind_code}, token=token)
    post(client, "/parent/consume", {"student_id": s1.id, "item": "看手机", "points": 10}, token=token)

    post(client, "/parent/unbind", {"student_id": s1.id}, token=token)
    refresh()

    assert s1.total_points == 90
    logs = db.scalars(
        select(PointLog).where(PointLog.student_id == s1.id, PointLog.type == POINT_TYPE_CONSUME)
    ).all()
    assert len(logs) == 1  # 流水保留，可追溯