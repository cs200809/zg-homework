"""P1.5 admin 接口测试（PRD 5.8.1、5.8.2、5.8.5）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据。
"""

import pytest

from app.db.repo import Repo
from app.models.constants import (
    INVITE_REVOKED,
    INVITE_UNUSED,
    INVITE_USED,
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
    STATUS_ACTIVE,
    STATUS_DISABLED,
)


def admin_post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


# ==================== 权限隔离 ====================


@pytest.mark.parametrize(
    "role", [ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT]
)
def test_non_admin_cannot_access_admin_api(client, make_user, login, role):
    """非 admin 访问 admin 接口一律 403（PRD 8）。"""
    token = login(*make_user(role, role))
    r = admin_post(client, "/admin/stats/overview", token=token)
    assert r.status_code == 403


def test_admin_api_requires_token(client):
    r = admin_post(client, "/admin/stats/overview")
    assert r.status_code == 401


def test_student_cannot_disable_user(client, make_user, login):
    """学生无权禁用他人。"""
    victim, _ = make_user(ROLE_STUDENT, "vic")
    token = login(*make_user(ROLE_STUDENT, "atk"))
    r = admin_post(client, "/admin/users/disable", {"user_id": victim.id}, token=token)
    assert r.status_code == 403


# ==================== 5.8.1 邀请码管理 ====================


def test_invite_create_batch(client, admin_token):
    """批量生成 1~50 个（PRD 5.8.1）。"""
    r = admin_post(client, "/admin/invite/create", {"count": 5}, token=admin_token)
    assert r.status_code == 200
    codes = r.json()["data"]["codes"]
    assert len(codes) == 5
    assert len(set(codes)) == 5  # 不重复
    assert all(len(c) == 12 for c in codes)


def test_invite_create_default_expire_7_days(client, admin_token, db):
    """有效期默认 7 天（PRD 5.8.1）。"""
    r = admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token)
    code = r.json()["data"]["codes"][0]

    invite = Repo(db).get_invite_by_code(code)
    assert invite.status == INVITE_UNUSED
    delta = invite.expire_at - invite.created_at
    assert 6.9 < delta.days < 7.1


def test_invite_create_custom_expire_days(client, admin_token, db):
    r = admin_post(client, "/admin/invite/create", {"count": 1, "expire_days": 30}, token=admin_token)
    code = r.json()["data"]["codes"][0]
    invite = Repo(db).get_invite_by_code(code)
    assert 29.9 < (invite.expire_at - invite.created_at).days < 30.1


def test_invite_create_count_out_of_range(client, admin_token):
    """count 超出 1~50 拒绝。"""
    assert admin_post(client, "/admin/invite/create", {"count": 0}, token=admin_token).status_code == 400
    assert admin_post(client, "/admin/invite/create", {"count": 51}, token=admin_token).status_code == 400


def test_invite_create_max_50(client, admin_token):
    r = admin_post(client, "/admin/invite/create", {"count": 50}, token=admin_token)
    assert r.status_code == 200
    assert len(r.json()["data"]["codes"]) == 50


def test_invite_list_paged(client, admin_token):
    """分页返回 {list, total, page, size}（PRD 3.2）。"""
    admin_post(client, "/admin/invite/create", {"count": 3}, token=admin_token)
    r = admin_post(client, "/admin/invite/list", {"page": 1, "size": 2}, token=admin_token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"list", "total", "page", "size"}
    assert len(data["list"]) == 2
    assert data["total"] >= 3


def test_invite_list_filter_by_status(client, admin_token):
    """按状态筛选（PRD 5.8.1）。"""
    admin_post(client, "/admin/invite/create", {"count": 2}, token=admin_token)
    r = admin_post(client, "/admin/invite/list", {"status": INVITE_UNUSED, "page": 1, "size": 50}, token=admin_token)
    assert r.status_code == 200
    assert all(i["status"] == INVITE_UNUSED for i in r.json()["data"]["list"])


def test_invite_list_invalid_status(client, admin_token):
    r = admin_post(client, "/admin/invite/list", {"status": "bogus"}, token=admin_token)
    assert r.status_code == 400


def test_invite_revoke(client, admin_token, db, refresh):
    """撤销未使用码（PRD 5.8.1）。"""
    code = admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token).json()["data"]["codes"][0]
    invite_id = Repo(db).get_invite_by_code(code).id

    r = admin_post(client, "/admin/invite/revoke", {"code_id": invite_id}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == INVITE_REVOKED
    refresh()
    assert Repo(db).get_invite_by_code(code).status == INVITE_REVOKED


def test_invite_revoke_used_code_fails(client, admin_token, db, refresh, uname):
    """已使用的码不可撤销（PRD 5.8.1「撤销未使用码」）。"""
    code = admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token).json()["data"]["codes"][0]

    # 用该码注册老师 → 状态变 used
    client.post("/auth/register", json={
        "username": uname("tu"), "password": "pass123", "role": ROLE_TEACHER,
        "teacher_invite_code": code,
    })
    refresh()
    invite_id = Repo(db).get_invite_by_code(code).id

    r = admin_post(client, "/admin/invite/revoke", {"code_id": invite_id}, token=admin_token)
    assert r.status_code == 400
    assert "只能撤销未使用的邀请码" in r.json()["message"]


def test_invite_revoke_already_revoked_fails(client, admin_token, db):
    code = admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token).json()["data"]["codes"][0]
    invite_id = Repo(db).get_invite_by_code(code).id

    assert admin_post(client, "/admin/invite/revoke", {"code_id": invite_id}, token=admin_token).status_code == 200
    r = admin_post(client, "/admin/invite/revoke", {"code_id": invite_id}, token=admin_token)
    assert r.status_code == 400


def test_invite_revoke_nonexistent(client, admin_token):
    r = admin_post(client, "/admin/invite/revoke", {"code_id": 999999999}, token=admin_token)
    assert r.status_code == 404


def test_generated_code_can_register_teacher(client, admin_token, uname):
    """生成的邀请码可直接用于老师注册（端到端）。"""
    code = admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token).json()["data"]["codes"][0]
    r = client.post("/auth/register", json={
        "username": uname("tg"), "password": "pass123", "role": ROLE_TEACHER,
        "teacher_invite_code": code,
    })
    assert r.status_code == 200
    assert r.json()["data"]["user"]["role"] == "teacher"


def test_invite_actions_written_to_admin_log(client, admin_token, db):
    """敏感操作写审计日志（PRD 10.1）。"""
    from app.utils.deps import decode_access_token

    # 审计日志记的是实际操作者（临时 admin 账号），不是真实 admin。
    actor_id = decode_access_token(admin_token)["user_id"]
    admin_post(client, "/admin/invite/create", {"count": 1}, token=admin_token)

    from app.models.entities import AdminLog
    from sqlalchemy import select

    logs = db.scalars(
        select(AdminLog).where(AdminLog.admin_id == actor_id, AdminLog.action == "invite_create")
    ).all()
    assert len(logs) >= 1


# ==================== 5.8.2 用户管理 ====================


@pytest.mark.parametrize("role", [ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT])
def test_admin_can_disable_each_role(client, admin_token, make_user, role):
    """admin 可禁用 teacher/student/parent（PRD 5.8.2）。"""
    target, _ = make_user(role, "tg")
    r = admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == STATUS_DISABLED


@pytest.mark.parametrize("role", [ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT])
def test_admin_can_enable_each_role(client, admin_token, make_user, role):
    target, _ = make_user(role, "tg")
    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    r = admin_post(client, "/admin/users/enable", {"user_id": target.id}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == STATUS_ACTIVE


def test_admin_cannot_disable_admin_itself(client, admin_token, db):
    """admin 无法禁用自己，返回 400（PRD 5.8.2、第 12 节验收）。"""
    from app.utils.deps import decode_access_token

    # 禁用「操作者自己」——即 admin_token 对应的那��� admin 账号。
    # 不是真实 admin：测试不应把真实 admin 卷进来。
    actor_id = decode_access_token(admin_token)["user_id"]
    r = admin_post(client, "/admin/users/disable", {"user_id": actor_id}, token=admin_token)
    assert r.status_code == 400
    assert "不可操作 admin" in r.json()["message"]


def test_admin_cannot_disable_other_admin(client, admin_token, make_user):
    """admin 无法禁用其他 admin（PRD 8）。"""
    other, _ = make_user(ROLE_ADMIN, "adm")
    r = admin_post(client, "/admin/users/disable", {"user_id": other.id}, token=admin_token)
    assert r.status_code == 400


def test_admin_cannot_enable_admin(client, admin_token, make_user):
    other, _ = make_user(ROLE_ADMIN, "adm")
    r = admin_post(client, "/admin/users/enable", {"user_id": other.id}, token=admin_token)
    assert r.status_code == 400


def test_admin_cannot_reset_admin_password(client, admin_token, make_user):
    other, _ = make_user(ROLE_ADMIN, "adm")
    r = admin_post(client, "/admin/users/reset-password", {"user_id": other.id}, token=admin_token)
    assert r.status_code == 400


def test_disable_twice_fails(client, admin_token, make_user):
    """重复禁用返回 400。"""
    target, _ = make_user(ROLE_STUDENT, "tg")
    assert admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token).status_code == 200
    r = admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    assert r.status_code == 400


def test_disable_nonexistent_user(client, admin_token):
    r = admin_post(client, "/admin/users/disable", {"user_id": 999999999}, token=admin_token)
    assert r.status_code == 404


def test_disabled_user_cannot_login(client, admin_token, make_user):
    """禁用后无法登录（PRD 第 12 节验收）。"""
    target, password = make_user(ROLE_STUDENT, "tg")
    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)

    r = client.post("/auth/login", json={"username": target.username, "password": password})
    assert r.status_code == 403


def test_disabled_user_token_invalidated_immediately(client, admin_token, make_user, login):
    """禁用后已有 JWT 立即失效（PRD 5.8.2）。"""
    target, password = make_user(ROLE_STUDENT, "tg")
    token = login(target.username, password)
    assert client.post("/auth/me", json={}, headers={"Authorization": f"Bearer {token}"}).status_code == 200

    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    r = client.post("/auth/me", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_re_enabled_user_can_login_again(client, admin_token, make_user):
    target, password = make_user(ROLE_STUDENT, "tg")
    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    admin_post(client, "/admin/users/enable", {"user_id": target.id}, token=admin_token)

    assert client.post("/auth/login", json={"username": target.username, "password": password}).status_code == 200


def test_reset_password_generates_temp_and_forces_change(client, admin_token, make_user):
    """重置密码生成临时密码并强制改密（PRD 5.8.2）。"""
    target, old_password = make_user(ROLE_STUDENT, "tg")
    r = admin_post(client, "/admin/users/reset-password", {"user_id": target.id}, token=admin_token)
    assert r.status_code == 200

    temp = r.json()["data"]["temp_password"]
    assert temp and len(temp) >= 8

    # 旧密码失效，临时密码可登录
    assert client.post("/auth/login", json={"username": target.username, "password": old_password}).status_code == 400
    login_r = client.post("/auth/login", json={"username": target.username, "password": temp})
    assert login_r.status_code == 200
    assert login_r.json()["data"]["must_change_password"] is True


def test_reset_password_temp_can_change(client, admin_token, make_user):
    """临时密码登录后可改密（PRD 第 12 节验收）。"""
    target, _ = make_user(ROLE_STUDENT, "tg")
    temp = admin_post(
        client, "/admin/users/reset-password", {"user_id": target.id}, token=admin_token
    ).json()["data"]["temp_password"]

    token = client.post("/auth/login", json={"username": target.username, "password": temp}).json()["data"]["token"]
    r = client.post(
        "/auth/change-password",
        json={"old_password": temp, "new_password": "brandnew123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_users_list_all(client, admin_token):
    r = admin_post(client, "/admin/users/list", {"page": 1, "size": 10}, token=admin_token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"list", "total", "page", "size"}
    assert "password_hash" not in str(data)


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT])
def test_users_list_filter_by_role(client, admin_token, make_user, role):
    make_user(role, "fg")
    r = admin_post(client, "/admin/users/list", {"role": role, "page": 1, "size": 50}, token=admin_token)
    assert r.status_code == 200
    assert all(u["role"] == role for u in r.json()["data"]["list"])


def test_users_list_filter_by_status(client, admin_token, make_user, refresh):
    """按状态筛选（PRD 5.8.2）。

    注意：库里会累积历史测试数据，禁用用户可能超过单页容量，
    因此用 keyword 精确定位本用例创建的用户。
    """
    target, _ = make_user(ROLE_STUDENT, "sg")
    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    refresh()

    r = admin_post(
        client,
        "/admin/users/list",
        {"status": STATUS_DISABLED, "keyword": target.username, "page": 1, "size": 50},
        token=admin_token,
    )
    assert r.status_code == 200
    items = r.json()["data"]["list"]
    assert items, "应能检索到刚禁用的用户"
    assert all(u["status"] == STATUS_DISABLED for u in items)
    assert all(u["id"] == target.id for u in items)


def test_users_list_keyword_search_username(client, admin_token, make_user):
    target, _ = make_user(ROLE_STUDENT, "kw1")
    r = admin_post(client, "/admin/users/list", {"keyword": target.username, "page": 1, "size": 50}, token=admin_token)
    assert r.status_code == 200
    items = r.json()["data"]["list"]
    assert len(items) >= 1
    assert all(target.username in u["username"] for u in items)


def test_users_list_keyword_search_nickname(client, admin_token, make_user):
    """关键词同时匹配昵称。"""
    target, _ = make_user(ROLE_STUDENT, "kw2", nickname="独特定位词")
    r = admin_post(client, "/admin/users/list", {"keyword": "独特定位词", "page": 1, "size": 50}, token=admin_token)
    items = r.json()["data"]["list"]
    assert any(u["id"] == target.id for u in items)


def test_users_list_invalid_role(client, admin_token):
    r = admin_post(client, "/admin/users/list", {"role": "bogus"}, token=admin_token)
    assert r.status_code == 400


def test_users_list_invalid_status(client, admin_token):
    r = admin_post(client, "/admin/users/list", {"status": "bogus"}, token=admin_token)
    assert r.status_code == 400


def test_users_list_pagination(client, admin_token, make_user):
    for _ in range(3):
        make_user(ROLE_STUDENT, "pg")
    r = admin_post(client, "/admin/users/list", {"page": 1, "size": 2}, token=admin_token)
    data = r.json()["data"]
    assert len(data["list"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1 and data["size"] == 2


def test_users_list_page_size_limit(client, admin_token):
    assert admin_post(client, "/admin/users/list", {"size": 101}, token=admin_token).status_code == 400


def test_users_detail(client, admin_token, make_user):
    target, _ = make_user(ROLE_STUDENT, "dt")
    r = admin_post(client, "/admin/users/detail", {"user_id": target.id}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["user"]["id"] == target.id
    assert "password_hash" not in str(r.json())


def test_users_detail_nonexistent(client, admin_token):
    r = admin_post(client, "/admin/users/detail", {"user_id": 999999999}, token=admin_token)
    assert r.status_code == 404


def test_user_actions_written_to_admin_log(client, admin_token, db, refresh, make_user):
    """禁用/启用/重置密码写审计日志（PRD 10.1）。"""
    from app.utils.deps import decode_access_token

    target, _ = make_user(ROLE_STUDENT, "lg")
    # 审计日志记的是**实际操作者**。admin_token 夹具用的是独立的临时 admin
    # 账号（不再覆盖真实 admin 的密码），因此要从 token 里取操作者 id，
    # 而不能想当然地假设是真实 admin。
    actor_id = decode_access_token(admin_token)["user_id"]

    admin_post(client, "/admin/users/disable", {"user_id": target.id}, token=admin_token)
    admin_post(client, "/admin/users/enable", {"user_id": target.id}, token=admin_token)
    admin_post(client, "/admin/users/reset-password", {"user_id": target.id}, token=admin_token)
    refresh()

    from sqlalchemy import select

    from app.models.entities import AdminLog

    actions = set(
        db.scalars(
            select(AdminLog.action).where(
                AdminLog.admin_id == actor_id,
                AdminLog.target_id == target.id,
            )
        ).all()
    )
    assert {"user_disable", "user_enable", "user_reset_password"} <= actions


# ==================== 5.8.5 统计 ====================


def test_stats_overview(client, admin_token):
    """全局统计（PRD 5.8.5）。"""
    r = admin_post(client, "/admin/stats/overview", token=admin_token)
    assert r.status_code == 200
    data = r.json()["data"]
    for key in ("user_count", "class_count", "homework_count", "point_total"):
        assert key in data
    assert data["user_count"] > 0


def test_stats_overview_accepts_empty_body(client, admin_token):
    """无入参接口：客户端传空 Body 也必须成功（PRD 全 POST + Body 约定）。"""
    r = client.post("/admin/stats/overview", json={}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["code"] == 0


def test_stats_overview_requires_admin(client, make_user, login):
    token = login(*make_user(ROLE_TEACHER, "tt"))
    assert admin_post(client, "/admin/stats/overview", token=token).status_code == 403


def test_classes_list(client, admin_token):
    """班级列表（PRD 5.8.5）。"""
    r = admin_post(client, "/admin/classes/list", {"page": 1, "size": 20}, token=admin_token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"list", "total", "page", "size"}
    if data["list"]:
        item = data["list"][0]
        for key in ("id", "name", "invite_code", "teacher_name", "student_count"):
            assert key in item


def test_classes_list_requires_admin(client, make_user, login):
    token = login(*make_user(ROLE_STUDENT, "cs"))
    assert admin_post(client, "/admin/classes/list", token=token).status_code == 403