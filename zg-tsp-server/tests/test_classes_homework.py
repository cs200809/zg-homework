"""P2 班级与作业测试（PRD 5.2、5.3）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

from datetime import datetime, timedelta

import pytest

from app.db.repo import Repo
from app.models.constants import (
    HOMEWORK_DOING,
    HOMEWORK_LATE,
    HOMEWORK_NOT_STARTED,
    HOMEWORK_SUBMITTED,
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.services.point_rule_service import rule_service


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


def post_form(client, path, data=None, token=None):
    """multipart 提交（PRD 5.3：/homework/submit）。"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, data=data or {}, headers=headers)


@pytest.fixture(autouse=True)
def _clear_cache():
    rule_service.invalidate()
    yield
    rule_service.invalidate()


@pytest.fixture
def set_rule(client, admin_token, db):
    """显式设置积分规则（规则表是共享状态，见 conftest 顶部说明）。"""

    def _set(rule_key: str, **fields) -> None:
        r = post(client, "/admin/rules/update", {"rule_key": rule_key, **fields}, token=admin_token)
        assert r.status_code == 200, r.text
        db.rollback()
        db.expire_all()
        rule_service.invalidate(rule_key)

    return _set


# ==================== 5.2 班级管理 ====================


def test_teacher_create_class(client, login, make_user):
    """老师创建班级，生成 6 位邀请码（PRD 5.2）。"""
    teacher, pw = make_user(ROLE_TEACHER, "cls")
    r = post(client, "/classes/create", {"name": "三年二班"}, token=login(teacher, pw))
    assert r.status_code == 200
    klass = r.json()["data"]["class"]
    assert klass["name"] == "三年二班"
    assert len(klass["invite_code"]) == 6
    assert klass["teacher_id"] == teacher.id


def test_create_class_names_unique(client, login, make_user):
    for i in range(3):
        teacher, pw = make_user(ROLE_TEACHER, "cn")
        r = post(client, "/classes/create", {"name": f"唯一班{i}"}, token=login(teacher, pw))
        assert r.status_code == 200


def test_student_cannot_create_class(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "stu")
    r = post(client, "/classes/create", {"name": "越权班"}, token=login(student, pw))
    assert r.status_code == 403


def test_parent_cannot_create_class(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "par")
    assert post(client, "/classes/create", {"name": "x"}, token=login(parent, pw)).status_code == 403


def test_create_class_empty_name_rejected(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "cls")
    r = post(client, "/classes/create", {"name": ""}, token=login(teacher, pw))
    assert r.status_code == 400


def test_student_join_class(client, login, make_user, make_class, refresh):
    """学生凭邀请码加入（PRD 5.2）。"""
    klass, teacher, tpw = make_class("加入测试班")
    student, spw = make_user(ROLE_STUDENT, "join")

    r = post(client, "/classes/join", {"invite_code": klass.invite_code}, token=login(student, spw))
    assert r.status_code == 200
    assert r.json()["data"]["class"]["id"] == klass.id

    refresh()
    assert student.class_id == klass.id


def test_join_class_wrong_code(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "join")
    r = post(client, "/classes/join", {"invite_code": "WRONG1"}, token=login(student, pw))
    assert r.status_code == 404


def test_join_class_only_one_class(client, login, make_user, make_class, refresh):
    """一个学生只属一个班级（PRD 5.2、决策 3）。"""
    k1, _, _ = make_class("班A")
    k2, _, _ = make_class("班B")
    student, pw = make_user(ROLE_STUDENT, "one")

    assert post(client, "/classes/join", {"invite_code": k1.invite_code}, token=login(student, pw)).status_code == 200

    # 第二次加入应失败
    r = post(client, "/classes/join", {"invite_code": k2.invite_code}, token=login(student, pw))
    assert r.status_code == 400
    assert "不能重复加入" in r.json()["message"]

    refresh()
    assert student.class_id == k1.id  # 仍属原班


def test_teacher_cannot_join_class(client, login, make_user, make_class):
    klass, _, _ = make_class()
    teacher, pw = make_user(ROLE_TEACHER, "tj")
    assert post(client, "/classes/join", {"invite_code": klass.invite_code}, token=login(teacher, pw)).status_code == 403


def test_class_my_for_teacher(client, login, make_user, make_class, refresh):
    """老师查看自己建的班。"""
    teacher, pw = make_user(ROLE_TEACHER, "my")
    klass, _, _ = make_class("我的班", teacher=teacher)

    r = post(client, "/classes/my", token=login(teacher, pw))
    assert r.status_code == 200
    classes = r.json()["data"]["classes"]
    assert any(c["id"] == klass.id for c in classes)


def test_class_my_for_student(client, login, make_user, make_class, db, refresh):
    klass, _, _ = make_class()
    student, pw = make_user(ROLE_STUDENT, "my")
    student.class_id = klass.id
    db.commit()
    refresh()

    r = post(client, "/classes/my", token=login(student, pw))
    assert r.status_code == 200
    classes = r.json()["data"]["classes"]
    assert len(classes) == 1
    assert classes[0]["id"] == klass.id


def test_class_my_student_without_class(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "nc")
    r = post(client, "/classes/my", token=login(student, pw))
    assert r.status_code == 200
    assert r.json()["data"]["classes"] == []


def test_class_students_list(client, login, make_user, make_class, db, refresh):
    """老师查看班级学生（PRD 5.2）。"""
    klass, teacher, tpw = make_class("学生列表班", teacher=None)
    student, spw = make_user(ROLE_STUDENT, "sl")
    student.class_id = klass.id
    db.commit()
    refresh()

    r = post(client, "/classes/students", {"class_id": klass.id}, token=login(teacher, tpw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["class"]["student_count"] == 1
    assert any(s["id"] == student.id for s in data["students"])
    assert "password_hash" not in str(data)


def test_class_students_other_teacher_forbidden(client, login, make_user, make_class):
    """不能查看别人班的学生（PRD 8）。"""
    klass, _, _ = make_class("A班")
    other, opw = make_user(ROLE_TEACHER, "oth")

    r = post(client, "/classes/students", {"class_id": klass.id}, token=login(other, opw))
    assert r.status_code == 403


def test_remove_student(client, login, make_user, make_class, db, refresh):
    """老师移除学生（PRD 5.2）。"""
    klass, teacher, tpw = make_class()
    student, spw = make_user(ROLE_STUDENT, "rm")
    student.class_id = klass.id
    db.commit()
    refresh()

    r = post(
        client,
        "/classes/remove-student",
        {"class_id": klass.id, "student_id": student.id},
        token=login(teacher, tpw),
    )
    assert r.status_code == 200

    refresh()
    assert student.class_id is None


def test_remove_student_not_in_class(client, login, make_user, make_class):
    klass, teacher, tpw = make_class()
    other_stu, _ = make_user(ROLE_STUDENT, "other")

    r = post(
        client,
        "/classes/remove-student",
        {"class_id": klass.id, "student_id": other_stu.id},
        token=login(teacher, tpw),
    )
    assert r.status_code == 400
    assert "不属于此班级" in r.json()["message"]


def test_remove_student_other_teacher_forbidden(client, login, make_user, make_class, db, refresh):
    klass, _, _ = make_class()
    student, _ = make_user(ROLE_STUDENT, "rs")
    student.class_id = klass.id
    db.commit()
    refresh()

    other, opw = make_user(ROLE_TEACHER, "oo")
    r = post(
        client,
        "/classes/remove-student",
        {"class_id": klass.id, "student_id": student.id},
        token=login(other, opw),
    )
    assert r.status_code == 403


# ==================== 5.3 作业：老师端 ====================


@pytest.fixture
def klass_with_student(make_class, make_user, db):
    """(班级, 班主任, 班主任密码, 学生, 学生密码)"""
    klass, teacher, tpw = make_class("作业班")
    student, spw = make_user(ROLE_STUDENT, "hw")
    student.class_id = klass.id
    db.commit()
    return klass, teacher, tpw, student, spw


def test_teacher_create_homework(client, login, klass_with_student):
    """老师布置作业（PRD 5.3）。"""
    klass, teacher, tpw, _, _ = klass_with_student
    deadline = datetime.now() + timedelta(days=1)

    r = post(
        client,
        "/homework/create",
        {
            "class_id": klass.id,
            "title": "语文作文",
            "description": "写一篇 300 字作文",
            "subject": "语文",
            "deadline": deadline.isoformat(),
        },
        token=login(teacher, tpw),
    )
    assert r.status_code == 200
    hw = r.json()["data"]["homework"]
    assert hw["title"] == "语文作文"
    assert hw["subject"] == "语文"


def test_create_homework_other_class_forbidden(client, login, make_user, make_class):
    """不能给别人的班布置作业（PRD 8）。"""
    klass, _, _ = make_class("别人班")
    other, opw = make_user(ROLE_TEACHER, "oo")

    r = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "越权作业", "deadline": datetime.now().isoformat()},
        token=login(other, opw),
    )
    assert r.status_code == 403


def test_student_cannot_create_homework(client, login, klass_with_student):
    klass, _, _, student, spw = klass_with_student
    r = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "x", "deadline": datetime.now().isoformat()},
        token=login(student, spw),
    )
    assert r.status_code == 403


def test_homework_list_paged(client, login, klass_with_student):
    klass, teacher, tpw, _, _ = klass_with_student
    for i in range(3):
        post(
            client,
            "/homework/create",
            {"class_id": klass.id, "title": f"作业{i}", "deadline": (datetime.now() + timedelta(days=i + 1)).isoformat()},
            token=login(teacher, tpw),
        )

    r = post(client, "/homework/list", {"class_id": klass.id, "page": 1, "size": 2}, token=login(teacher, tpw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["list"]) == 2
    assert data["total"] == 3


def test_homework_delete_when_no_submission(client, login, klass_with_student, refresh, db):
    """无人提交时可删除（PRD 5.3）。"""
    klass, teacher, tpw, _, _ = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "待删除", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    r = post(client, "/homework/delete", {"homework_id": hw_id}, token=login(teacher, tpw))
    assert r.status_code == 200

    refresh()
    assert Repo(db).get_homework_by_id(hw_id) is None


def test_homework_delete_blocked_after_submission(client, login, klass_with_student, set_rule):
    """有人提交后不可删除（PRD 5.3、第 12 节验收）。"""
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student

    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "已提交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    post(client, "/homework/start", {"homework_id": hw_id}, token=login(student, spw))
    post_form(
        client,
        "/homework/submit",
        data={"homework_id": hw_id, "text_content": "答案"},
        token=login(student, spw),
    )

    r = post(client, "/homework/delete", {"homework_id": hw_id}, token=login(teacher, tpw))
    assert r.status_code == 400
    assert "不可删除" in r.json()["message"]


# ==================== 5.3 作业：学生端 ====================


def test_homework_today(client, login, klass_with_student):
    """学生端今日作业（PRD 5.3、9 学生端首页）。"""
    klass, teacher, tpw, student, spw = klass_with_student
    today_end = datetime.now().replace(hour=23, minute=59)

    post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "今日作业", "deadline": today_end.isoformat()},
        token=login(teacher, tpw),
    )

    r = post(client, "/homework/today", token=login(student, spw))
    assert r.status_code == 200
    items = r.json()["data"]["list"]
    assert len(items) == 1
    assert items[0]["title"] == "今日作业"
    assert items[0]["my_status"] == HOMEWORK_NOT_STARTED


def test_homework_today_student_without_class(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "nc")
    r = post(client, "/homework/today", token=login(student, pw))
    assert r.status_code == 200
    assert r.json()["data"]["list"] == []


def test_homework_start_records_time(client, login, klass_with_student, refresh, db):
    """start 记录 start_time（PRD 5.3）。"""
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "打点", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    r = post(client, "/homework/start", {"homework_id": hw_id}, token=login(student, spw))
    assert r.status_code == 200
    rec = r.json()["data"]["record"]
    assert rec["start_time"] is not None
    assert rec["status"] == HOMEWORK_DOING


def test_homework_start_not_overwritten(client, login, klass_with_student, refresh, db):
    """重复点击不覆盖 start_time（PRD 5.3、第 12 节验收）。"""
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "不覆盖", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    token = login(student, spw)
    first = post(client, "/homework/start", {"homework_id": hw_id}, token=token).json()["data"]
    assert first["already_started"] is False

    refresh()
    original_start = Repo(db).get_homework_record(hw_id, student.id).start_time

    second = post(client, "/homework/start", {"homework_id": hw_id}, token=token).json()["data"]
    assert second["already_started"] is True

    refresh()
    assert Repo(db).get_homework_record(hw_id, student.id).start_time == original_start


def test_homework_submit_on_time(client, login, klass_with_student, set_rule, refresh, db):
    """按时提交：状态 submitted，发 homework_on_time 积分（PRD 4.2、第 12 节验收）。"""
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student

    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "按时交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    token = login(student, spw)
    post(client, "/homework/start", {"homework_id": hw_id}, token=token)
    r = post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "答案"}, token=token)

    assert r.status_code == 200
    rec = r.json()["data"]["record"]
    assert rec["status"] == HOMEWORK_SUBMITTED
    assert rec["submit_time"] is not None
    assert rec["points"] == 10

    refresh()
    assert student.total_points == 10


def test_homework_submit_late(client, login, klass_with_student, set_rule, refresh, db):
    """超截止时间标记 late，发 homework_late 积分（PRD 5.3、第 12 节验收）。"""
    set_rule("homework_late", points=5, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student

    # 截止时间已过
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "迟交", "deadline": (datetime.now() - timedelta(hours=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    token = login(student, spw)
    r = post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "补交"}, token=token)

    assert r.status_code == 200
    rec = r.json()["data"]["record"]
    assert rec["status"] == HOMEWORK_LATE
    assert rec["points"] == 5


def test_homework_submit_duplicate_rejected(client, login, klass_with_student, set_rule):
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "重复交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    token = login(student, spw)
    post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "第一次"}, token=token)
    r = post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "第二次"}, token=token)
    assert r.status_code == 400
    assert "重复提交" in r.json()["message"]


def test_homework_submit_empty_rejected(client, login, klass_with_student):
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "空提交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    r = post_form(client, "/homework/submit", data={"homework_id": hw_id}, token=login(student, spw))
    assert r.status_code == 400


def test_homework_short_duration_flagged_suspicious(client, login, klass_with_student, set_rule):
    """用时 <1 分钟标记异常待审核（PRD 5.3、第 12 节验收）。"""
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "秒交", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    token = login(student, spw)
    post(client, "/homework/start", {"homework_id": hw_id}, token=token)
    r = post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "秒答"}, token=token)

    rec = r.json()["data"]["record"]
    assert rec["duration_minutes"] == 0
    assert rec["suspicious"] is True  # 待老师审核


def test_homework_records_visible_to_teacher(client, login, klass_with_student, set_rule, refresh):
    """老师能看到开始时间与用时（PRD 5.3、第 12 节验收）。"""
    set_rule("homework_on_time", points=10, daily_limit=None, enabled=True)
    klass, teacher, tpw, student, spw = klass_with_student
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "完成情况", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    stu_token = login(student, spw)
    post(client, "/homework/start", {"homework_id": hw_id}, token=stu_token)
    post_form(client, "/homework/submit", data={"homework_id": hw_id, "text_content": "答案"}, token=stu_token)

    r = post(client, "/homework/records", {"homework_id": hw_id}, token=login(teacher, tpw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_students"] == 1
    assert data["submitted_count"] == 1

    row = data["records"][0]
    assert row["student_id"] == student.id
    assert row["status"] == HOMEWORK_SUBMITTED
    assert row["start_time"] is not None
    assert row["submit_time"] is not None
    assert row["points"] == 10
    assert "password_hash" not in str(data)


def test_homework_records_other_teacher_forbidden(client, login, make_user, make_class):
    klass, _, _ = make_class()
    other, opw = make_user(ROLE_TEACHER, "oo")
    r = post(client, "/homework/records", {"homework_id": 999999}, token=login(other, opw))
    assert r.status_code in (403, 404)


def test_homework_detail_student_other_class_forbidden(client, login, make_user, make_class):
    klass, teacher, tpw = make_class("详情班")
    hw_id = post(
        client,
        "/homework/create",
        {"class_id": klass.id, "title": "别的班作业", "deadline": (datetime.now() + timedelta(days=1)).isoformat()},
        token=login(teacher, tpw),
    ).json()["data"]["homework"]["id"]

    outsider, opw = make_user(ROLE_STUDENT, "out")
    r = post(client, "/homework/detail", {"homework_id": hw_id}, token=login(outsider, opw))
    assert r.status_code == 403