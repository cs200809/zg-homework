"""P1 认证接口测试（覆盖 PRD 第 12 节验收标准中的认证部分）。

约定：只增不删 —— 用例使用唯一用户名，不清理数据，断言基于当次新增的记录。
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.db.repo import Repo
from app.db.session import SessionLocal
from app.models.constants import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER, STATUS_DISABLED
from app.utils.deps import (
    get_current_user,
    get_verified_user,
    require_admin,
    require_roles,
)
from app.utils.response import ok


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


# ---------------- 登录 ----------------


def test_login_success(client, make_user):
    user, password = make_user(ROLE_STUDENT, "stu")
    r = post(client, "/auth/login", {"username": user.username, "password": password})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["role"] == "student"
    assert "password_hash" not in str(body)  # 绝不能外泄


def test_login_each_role(client, make_user):
    """四角色均可登录。"""
    for role in (ROLE_ADMIN, ROLE_TEACHER, "student", "parent"):
        user, password = make_user(role, role)
        r = post(client, "/auth/login", {"username": user.username, "password": password})
        assert r.status_code == 200, f"{role} 登录失败"
        assert r.json()["data"]["user"]["role"] == role


def test_login_wrong_password(client, make_user):
    user, _ = make_user(ROLE_STUDENT, "stu")
    r = post(client, "/auth/login", {"username": user.username, "password": "wrong"})
    assert r.status_code == 400
    assert r.json()["code"] == 400


def test_login_unknown_user(client, uname):
    r = post(client, "/auth/login", {"username": uname("ghost"), "password": "x"})
    assert r.status_code == 400


def test_login_disabled_user(client, make_user, set_user_status):
    """被禁用用户登录返回 403（PRD 5.1）。"""
    user, password = make_user(ROLE_STUDENT, "stu")
    set_user_status(user.id, STATUS_DISABLED)

    r = post(client, "/auth/login", {"username": user.username, "password": password})
    assert r.status_code == 403
    assert r.json()["code"] == 403


def test_jwt_expires_in_7_days(client, make_user, login):
    """JWT 有效期 7 天（PRD 3.3）。"""
    import jose

    user, password = make_user(ROLE_STUDENT, "stu")
    token = login(user.username, password)

    payload = jose.jwt.get_unverified_claims(token)
    remaining = datetime.fromtimestamp(payload["exp"], tz=timezone.utc) - datetime.now(timezone.utc)
    # 用小时而非 .days（后者会向下取整，7 天 - 数秒 = 6 天导致误判）
    hours = remaining.total_seconds() / 3600
    assert 167 < hours <= 168


def test_jwt_contains_user_id_and_role(client, make_user, login):
    import jose

    user, password = make_user(ROLE_TEACHER, "tch")
    payload = jose.jwt.get_unverified_claims(login(user.username, password))
    assert payload["user_id"] == user.id
    assert payload["role"] == ROLE_TEACHER


# ---------------- /auth/me ----------------


def test_me_requires_token(client):
    r = post(client, "/auth/me")
    assert r.status_code == 401


def test_me_requires_bearer_format(client, make_user, login):
    token = login(*make_user(ROLE_TEACHER, "tch"))
    r = client.post("/auth/me", json={}, headers={"Authorization": token})
    assert r.status_code == 401
    assert "Bearer" in r.json()["message"]


def test_me_returns_current_user(client, make_user, login):
    user, password = make_user(ROLE_TEACHER, "tch")
    r = post(client, "/auth/me", token=login(user.username, password))
    assert r.status_code == 200
    assert r.json()["data"]["user"]["username"] == user.username
    assert r.json()["data"]["user"]["role"] == ROLE_TEACHER


def test_disabled_user_token_invalidated_immediately(client, make_user, login, set_user_status):
    """禁用后已有 JWT 立即失效（PRD 3.3）—— 依赖每次查库校验 status。

    这条用例需要跨会话可见性，因此使用真实 commit 而非事务回滚。
    """
    user, password = make_user(ROLE_STUDENT, "stu")
    token = login(user.username, password)

    # 禁用前可用
    assert post(client, "/auth/me", token=token).status_code == 200

    set_user_status(user.id, STATUS_DISABLED)
    # 禁用后同一 token 立即 403
    assert post(client, "/auth/me", token=token).status_code == 403


def test_invalid_token_rejected(client):
    assert post(client, "/auth/me", token="not-a-real-token").status_code == 401


def test_tampered_token_rejected(client, make_user, login):
    """篡改 token 签名后应失效。"""
    token = login(*make_user(ROLE_STUDENT, "stu"))
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    assert post(client, "/auth/me", token=tampered).status_code == 401


# ---------------- 注册 ----------------


def test_register_student(client, uname, db):
    r = post(client, "/auth/register", {"username": uname("stu"), "password": "pass123", "role": "student"})
    assert r.status_code == 200
    user = r.json()["data"]["user"]
    assert user["bind_code"]  # 学生自动生成绑定码

    # 数据确实落库
    assert Repo(db).get_user_by_username(user["username"]) is not None


def test_register_parent(client, uname):
    r = post(client, "/auth/register", {"username": uname("par"), "password": "pass123", "role": "parent"})
    assert r.status_code == 200
    assert r.json()["data"]["user"]["bind_code"] is None  # 家长无绑定码


def test_register_duplicate_username(client, uname):
    name = uname("dup")
    body = {"username": name, "password": "pass123", "role": "student"}
    assert post(client, "/auth/register", body).status_code == 200
    r = post(client, "/auth/register", body)
    assert r.status_code == 400
    assert "已存在" in r.json()["message"]


def test_register_admin_not_allowed(client, uname):
    """admin 不开放注册（PRD 5.1）。"""
    r = post(client, "/auth/register", {"username": uname("adm"), "password": "pass123", "role": "admin"})
    assert r.status_code == 400
    assert "admin 不开放注册" in r.json()["message"]


def test_register_short_password(client, uname):
    r = post(client, "/auth/register", {"username": uname("sp"), "password": "123", "role": "student"})
    assert r.status_code == 400


def test_register_username_too_short(client, uname):
    r = post(client, "/auth/register", {"username": "ab", "password": "pass123", "role": "student"})
    assert r.status_code == 400


def test_register_nickname_and_chinese(client, uname):
    """中文昵称正确落库（utf8mb4，PRD 2.1）。"""
    name = uname("cn")
    r = post(
        client,
        "/auth/register",
        {"username": name, "password": "pass123", "role": "student", "nickname": "张三丰"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["user"]["nickname"] == "张三丰"


# ---------------- 老师邀请码 ----------------


def test_register_teacher_without_invite_code_fails(client, uname):
    r = post(client, "/auth/register", {"username": uname("tno"), "password": "pass123", "role": "teacher"})
    assert r.status_code == 400
    assert "邀请码" in r.json()["message"]


def test_register_teacher_with_invalid_invite_code_fails(client, uname):
    r = post(
        client,
        "/auth/register",
        {"username": uname("tbad"), "password": "pass123", "role": "teacher", "teacher_invite_code": "NOPE123"},
    )
    assert r.status_code == 400
    assert "不存在" in r.json()["message"]


def test_register_teacher_with_valid_invite_code(client, make_invite, uname):
    code = make_invite("okinv")
    r = post(
        client,
        "/auth/register",
        {"username": uname("tok"), "password": "pass123", "role": "teacher", "teacher_invite_code": code},
    )
    assert r.status_code == 200
    assert r.json()["data"]["user"]["role"] == "teacher"


def test_invite_code_is_single_use(client, make_invite, uname, db):
    """一码一用（PRD 5.1、第 12 节验收）。"""
    code = make_invite("oneuse")
    body = {"username": uname("tu1"), "password": "pass123", "role": "teacher", "teacher_invite_code": code}
    assert post(client, "/auth/register", body).status_code == 200

    # 第二次使用同一码应失败
    r = post(client, "/auth/register", dict(body, username=uname("tu2")))
    assert r.status_code == 400
    assert "不可用" in r.json()["message"]

    # 邀请码已标记为 used 并记录使用者与时间
    invite = Repo(db).get_invite_by_code(code)
    assert invite.status == "used"
    assert invite.used_at is not None
    assert invite.used_by_user_id is not None


def test_expired_invite_code_rejected(client, make_invite, uname):
    code = make_invite("expinv", expire_at=datetime.now() - timedelta(days=1))
    r = post(
        client,
        "/auth/register",
        {"username": uname("texp"), "password": "pass123", "role": "teacher", "teacher_invite_code": code},
    )
    assert r.status_code == 400
    assert "过期" in r.json()["message"]


def test_unexpired_invite_code_accepted(client, make_invite, uname):
    code = make_invite("futur", expire_at=datetime.now() + timedelta(days=7))
    r = post(
        client,
        "/auth/register",
        {"username": uname("tfut"), "password": "pass123", "role": "teacher", "teacher_invite_code": code},
    )
    assert r.status_code == 200


def test_revoked_invite_code_rejected(client, make_invite, uname):
    code = make_invite("revo", status="revoked")
    r = post(
        client,
        "/auth/register",
        {"username": uname("trev"), "password": "pass123", "role": "teacher", "teacher_invite_code": code},
    )
    assert r.status_code == 400


# ---------------- 修改密码 ----------------


def test_change_password_success(client, make_user, login):
    user, password = make_user(ROLE_STUDENT, "stu")
    token = login(user.username, password)

    r = post(client, "/auth/change-password", {"old_password": password, "new_password": "newpass456"}, token=token)
    assert r.status_code == 200

    # 新密码可登录，旧密码不可
    assert post(client, "/auth/login", {"username": user.username, "password": "newpass456"}).status_code == 200
    assert post(client, "/auth/login", {"username": user.username, "password": password}).status_code == 400


def test_change_password_clears_must_change_flag(client, db, login):
    """admin 改密后强制改密标记解除（PRD 5.1）。"""
    from app.models.entities import User
    from app.utils.security import hash_password

    admin = Repo(db).get_user_by_username("admin")
    if admin is None:
        admin = User(username="admin", password_hash=hash_password("x"), role=ROLE_ADMIN)
        db.add(admin)
        db.commit()
        db.refresh(admin)

    admin.password_hash = hash_password("firstpass1")
    admin.must_change_password = True
    admin.status = "active"
    db.commit()

    token = login("admin", "firstpass1")
    r = post(client, "/auth/change-password", {"old_password": "firstpass1", "new_password": "brandnew123"}, token=token)
    assert r.status_code == 200

    db.refresh(admin)
    assert admin.must_change_password is False


def test_change_password_wrong_old(client, make_user, login):
    user, _ = make_user(ROLE_STUDENT, "stu")
    r = post(client, "/auth/change-password", {"old_password": "wrong", "new_password": "newpass456"}, token=login(user.username))
    assert r.status_code == 400


def test_change_password_same_as_old(client, make_user, login):
    user, password = make_user(ROLE_STUDENT, "stu")
    r = post(client, "/auth/change-password", {"old_password": password, "new_password": password}, token=login(user.username, password))
    assert r.status_code == 400


def test_change_password_requires_token(client):
    assert post(client, "/auth/change-password", {"old_password": "a", "new_password": "b"}).status_code == 401


# ---------------- 权限依赖 ----------------


def _probe_app(dependency):
    """构造一个只挂单个权限依赖的探针 app。

    注意：不能传 json body —— 依赖链里 `user: User = Depends(...)` 会被 FastAPI
    当作请求体参数，传入 ORM 实例会导致序列化错误。权限依赖只需 Header。
    """
    test_app = FastAPI()

    @test_app.post("/probe")
    async def probe(user=Depends(dependency)):
        return ok({"role": user.role})

    return TestClient(test_app, raise_server_exceptions=False)


def test_role_dependency_blocks_wrong_role(client, make_user, login):
    """require_roles 拦截角色不符的请求（PRD 8）。"""
    tc = _probe_app(require_roles(ROLE_ADMIN))
    token = login(*make_user(ROLE_TEACHER, "tch"))
    r = tc.post("/probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "admin" in r.json()["detail"]["message"]


def test_role_dependency_allows_matching_role(client, make_user, login):
    tc = _probe_app(require_roles(ROLE_TEACHER))
    token = login(*make_user(ROLE_TEACHER, "tch"))
    r = tc.post("/probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "teacher"


def test_require_admin_blocks_non_admin(client, make_user, login):
    tc = _probe_app(require_admin)
    token = login(*make_user(ROLE_TEACHER, "tch"))
    r = tc.post("/probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_require_admin_allows_admin(client, admin_token):
    tc = _probe_app(require_admin)
    r = tc.post("/probe", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "admin"


def test_admin_must_change_password_blocks_other_apis(client, db, login):
    """admin 未改密前访问业务接口 403（PRD 5.1）。"""
    from app.models.entities import User
    from app.utils.security import hash_password

    admin = Repo(db).get_user_by_username("admin")
    if admin is None:
        admin = User(username="admin", password_hash=hash_password("x"), role=ROLE_ADMIN)
        db.add(admin)
        db.commit()
        db.refresh(admin)

    admin.password_hash = hash_password("firstpass1")
    admin.must_change_password = True
    db.commit()

    token = login("admin", "firstpass1")

    session = SessionLocal()
    try:
        # token 本身有效（get_current_user 通过）
        user = get_current_user(authorization=f"Bearer {token}", db=session)
        assert user.role == "admin"
        assert user.must_change_password is True

        # 但业务接口依赖 get_verified_user，对未改密 admin 抛 403
        with pytest.raises(HTTPException) as exc_info:
            get_verified_user(user)
        assert exc_info.value.status_code == 403
    finally:
        session.close()


# ---------------- 响应格式 ----------------


def test_health_format(client):
    """统一响应格式（PRD 3.1）。"""
    r = client.post("/health")
    body = r.json()
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 0


def test_error_response_format(client, uname):
    """错误响应同样遵循 {code, message, data}（PRD 3.1）。"""
    r = post(client, "/auth/login", {"username": uname("ghost"), "password": "x"})
    body = r.json()
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 400
    assert body["data"] == {}


# ---------------- 持久化验证 ----------------


def test_data_persists_across_sessions(client, make_user, db):
    """数据落到 MySQL，跨会话可见（不再是内存 mock）。"""
    user, _ = make_user(ROLE_STUDENT, "stu")

    from app.db.session import SessionLocal

    other = SessionLocal()
    try:
        found = Repo(other).get_user_by_id(user.id)
        assert found is not None
        assert found.username == user.username
    finally:
        other.close()


def test_point_rules_seeded(client, db):
    """PRD 4.2 的 10 条积分规则已由种子写入。"""
    rules = Repo(db).list_point_rules()
    assert len(rules) == 10
    keys = {r.rule_key for r in rules}
    assert {"checkin_daily", "reading_per_minute", "game_idiom"} <= keys


def test_password_stored_as_bcrypt_hash(client, db, uname):
    """密码以 bcrypt 哈希存储，绝不明文落库。"""
    r = post(client, "/auth/register", {"username": uname("bc"), "password": "plaintext123", "role": "student"})
    assert r.status_code == 200

    user = Repo(db).get_user_by_username(r.json()["data"]["user"]["username"])
    assert user.password_hash != "plaintext123"
    assert user.password_hash.startswith("$2b$")  # bcrypt