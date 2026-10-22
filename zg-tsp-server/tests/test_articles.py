"""P5 课后阅读测试（PRD 5.5）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

import json
from datetime import date

import pytest

from app.db.repo import Repo
from app.models.constants import (
    ARTICLE_HIDDEN,
    ARTICLE_PUBLISHED,
    POINT_TYPE_READING,
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
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


@pytest.fixture
def reading_rules(set_rule):
    """PRD 4.2 的阅读规则默认值。"""
    set_rule(
        "reading_per_minute",
        points=1,
        daily_limit=30,
        extra_config=json.dumps({"single_article_limit": 10}),
        enabled=True,
    )
    set_rule("reading_finish", points=5, daily_limit=None, enabled=True)


@pytest.fixture
def article(client, login, make_user):
    """老师发布一篇文章，返回 (article_id, teacher, 密码)。"""
    teacher, tpw = make_user(ROLE_TEACHER, "art")
    r = post(
        client,
        "/articles/create",
        {"title": f"阅读{teacher.username}", "content": "正文内容"},
        token=login(teacher, tpw),
    )
    assert r.status_code == 200
    return r.json()["data"]["article"]["id"], teacher, tpw


# ==================== 发布与可见性 ====================


def test_teacher_create_article(client, login, make_user):
    """老师发布文章（PRD 5.5）。"""
    teacher, tpw = make_user(ROLE_TEACHER, "tc")
    r = post(client, "/articles/create", {"title": "小故事", "content": "从前有座山"}, token=login(teacher, tpw))
    assert r.status_code == 200
    art = r.json()["data"]["article"]
    assert art["created_role"] == "teacher"
    assert art["status"] == ARTICLE_PUBLISHED


def test_admin_create_article(client, admin_token):
    """admin 也可发布（PRD 5.5）。"""
    r = post(client, "/articles/create", {"title": "平台公告", "content": "内容"}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["article"]["created_role"] == "admin"


def test_student_cannot_create_article(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "sc")
    r = post(client, "/articles/create", {"title": "x", "content": "y"}, token=login(student, pw))
    assert r.status_code == 403


def test_parent_cannot_create_article(client, login, make_user):
    parent, pw = make_user(ROLE_PARENT, "pc")
    r = post(client, "/articles/create", {"title": "x", "content": "y"}, token=login(parent, pw))
    assert r.status_code == 403


def test_student_only_sees_published(client, login, make_user, db, refresh):
    """学生端仅见 published（PRD 5.5、5.8.4）。"""
    teacher, tpw = make_user(ROLE_TEACHER, "ap")
    for i in range(2):
        post(client, "/articles/create", {"title": f"公开{i}", "content": "c"}, token=login(teacher, tpw))

    hidden = Repo(db).add_article(__import__("app.models.entities", fromlist=["Article"]).Article(
        author_id=teacher.id, created_role="teacher", title="隐藏文章", content="c", status=ARTICLE_HIDDEN,
    ))
    db.commit()
    refresh()

    student, spw = make_user(ROLE_STUDENT, "sv")
    r = post(client, "/articles/list", {"page": 1, "size": 50}, token=login(student, spw))
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()["data"]["list"]}
    assert hidden.id not in ids


def test_article_list_excludes_content(client, login, article):
    """列表不返回正文，节省流量。"""
    _, teacher, tpw = article
    r = post(client, "/articles/list", {"page": 1, "size": 10}, token=login(teacher, tpw))
    assert r.status_code == 200
    assert all("content" not in a for a in r.json()["data"]["list"])


def test_student_cannot_view_hidden_article(client, login, make_user, db, refresh, article):
    """学生不可查看 hidden 文章（PRD 5.5）。"""
    art_id, teacher, _ = article
    hidden = Repo(db).add_article(__import__("app.models.entities", fromlist=["Article"]).Article(
        author_id=teacher.id, created_role="teacher", title="隐藏", content="c", status=ARTICLE_HIDDEN,
    ))
    db.commit()
    refresh()

    student, pw = make_user(ROLE_STUDENT, "sh")
    r = post(client, "/articles/detail", {"article_id": hidden.id}, token=login(student, pw))
    assert r.status_code == 404


# ==================== 心跳与防挂机 ====================


def test_heartbeat_accumulates_time(client, login, make_user, article, db, refresh):
    """心跳累计阅读时长（PRD 5.5）。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "hb")
    token = login(student, pw)

    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["accepted"] is True
    assert data["duration_seconds"] == 30


def test_heartbeat_rejects_abnormal_interval(client, login, make_user, article, db, refresh):
    """间隔超出 30s±10s 判定挂机，不计时（PRD 5.5、第 12 节验收）。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "hba")
    token = login(student, pw)

    # 正常一次
    post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)

    # 声称读了 300 秒 —— 远超上限
    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 300}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["accepted"] is False
    assert "异常" in data["reason"]

    refresh()
    rec = Repo(db).get_reading_record(art_id, student.id, date.today())
    assert rec.duration_seconds == 30  # 未被挂机数据污染


def test_heartbeat_tolerance_boundary(client, login, make_user, article, db, refresh):
    """40 秒在 30+10 边界内，应被接受。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "hbt")
    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 40}, token=login(student, pw))
    assert r.json()["data"]["accepted"] is True


def test_heartbeat_41s_rejected(client, login, make_user, article):
    """超过 40 秒即判定异常。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "hb41")
    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 41}, token=login(student, pw))
    assert r.json()["data"]["accepted"] is False


def test_heartbeat_teacher_forbidden(client, login, article):
    art_id, teacher, tpw = article
    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=login(teacher, tpw))
    assert r.status_code == 403


# ==================== 阅读积分 ====================


def test_reading_points_per_minute(client, login, make_user, article, reading_rules, db, refresh):
    """每分钟 +1（PRD 5.5、4.2）。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "rp")
    token = login(student, pw)

    # 累计 60 秒 → 应发 1 分
    post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)
    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)
    data = r.json()["data"]
    assert data["duration_seconds"] == 60
    assert data["points_gained"] == 1

    refresh()
    assert student.total_points == 1


def test_reading_points_not_awarded_before_1min(client, login, make_user, article, reading_rules, db, refresh):
    """不足 1 分钟不发分。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "rpn")
    token = login(student, pw)

    r = post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 25}, token=token)
    assert r.json()["data"]["points_gained"] == 0

    refresh()
    assert student.total_points == 0


def test_finish_gives_bonus_once(client, login, make_user, article, reading_rules, db, refresh):
    """读完 +5，单篇 1 次（PRD 5.5、第 12 节验收）。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "fin")
    token = login(student, pw)

    r = post(client, "/articles/finish", {"article_id": art_id}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["already_finished"] is False
    assert data["points_gained"] == 5

    # 重复标记不再发
    r2 = post(client, "/articles/finish", {"article_id": art_id}, token=token)
    assert r2.json()["data"]["already_finished"] is True
    assert r2.json()["data"]["points_gained"] if "points_gained" in r2.json()["data"] else True

    refresh()
    assert student.total_points == 5


def test_finish_records_finished_flag(client, login, make_user, article, reading_rules, db, refresh):
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "fin2")
    post(client, "/articles/finish", {"article_id": art_id}, token=login(student, pw))
    refresh()

    rec = Repo(db).get_reading_record(art_id, student.id, date.today())
    assert rec.finished is True
    assert rec.points == 5


def test_disabled_reading_rule_gives_nothing(client, login, make_user, article, set_rule, db, refresh):
    """规则禁用不发放（PRD 6）。"""
    set_rule("reading_finish", points=5, enabled=False)
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "fd")

    r = post(client, "/articles/finish", {"article_id": art_id}, token=login(student, pw))
    assert r.json()["data"]["points_gained"] == 0

    refresh()
    assert student.total_points == 0


def test_reading_points_written_to_log(client, login, make_user, article, reading_rules, db, refresh):
    from sqlalchemy import select

    from app.models.entities import PointLog

    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "rl")
    token = login(student, pw)
    post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)
    post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=token)
    refresh()

    logs = db.scalars(
        select(PointLog).where(
            PointLog.student_id == student.id,
            PointLog.type == POINT_TYPE_READING,
        )
    ).all()
    assert len(logs) == 1
    assert logs[0].points == 1


def test_idle_heartbeat_gives_no_points(client, login, make_user, article, reading_rules, db, refresh):
    """挂机不产生积分（PRD 10.2、第 12 节验收）。"""
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "idl")
    token = login(student, pw)

    for _ in range(10):
        post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 300}, token=token)

    refresh()
    assert student.total_points == 0


# ==================== 阅读记录与删除 ====================


def test_teacher_sees_records_of_own_article(client, login, make_user, article, reading_rules):
    """老师查看自己文章的阅读记录（PRD 5.5）。"""
    art_id, teacher, tpw = article
    student, spw = make_user(ROLE_STUDENT, "rd")
    stu_token = login(student, spw)
    post(client, "/articles/heartbeat", {"article_id": art_id, "seconds": 30}, token=stu_token)
    post(client, "/articles/finish", {"article_id": art_id}, token=stu_token)

    r = post(client, "/articles/records", {"article_id": art_id}, token=login(teacher, tpw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["stats"]["reader_count"] == 1
    assert data["stats"]["finished_count"] == 1
    assert data["stats"]["total_duration_seconds"] == 30
    assert "password_hash" not in str(data)


def test_teacher_cannot_see_others_records(client, login, make_user, article):
    """不能查看别人文章的阅读记录（PRD 8）。"""
    art_id, _, _ = article
    other, opw = make_user(ROLE_TEACHER, "oth")
    r = post(client, "/articles/records", {"article_id": art_id}, token=login(other, opw))
    assert r.status_code == 403


def test_teacher_cannot_delete_others_article(client, login, make_user, article):
    """老师仅能删自己的文章（PRD 5.5）。"""
    art_id, _, _ = article
    other, opw = make_user(ROLE_TEACHER, "od")
    r = post(client, "/articles/delete", {"article_id": art_id}, token=login(other, opw))
    assert r.status_code == 403


def test_teacher_delete_own_article(client, login, article, db, refresh):
    art_id, teacher, tpw = article
    r = post(client, "/articles/delete", {"article_id": art_id}, token=login(teacher, tpw))
    assert r.status_code == 200

    refresh()
    assert Repo(db).get_article_by_id(art_id) is None


def test_admin_delete_any_article(client, admin_token, article, db, refresh):
    """admin 可删任意文章（PRD 5.8.4）。"""
    art_id, _, _ = article
    r = post(client, "/articles/delete", {"article_id": art_id}, token=admin_token)
    assert r.status_code == 200

    refresh()
    assert Repo(db).get_article_by_id(art_id) is None


def test_student_cannot_delete_article(client, login, make_user, article):
    art_id, _, _ = article
    student, pw = make_user(ROLE_STUDENT, "sd")
    r = post(client, "/articles/delete", {"article_id": art_id}, token=login(student, pw))
    assert r.status_code == 403


def test_records_requires_login(client, article):
    art_id, _, _ = article
    assert post(client, "/articles/records", {"article_id": art_id}).status_code == 401