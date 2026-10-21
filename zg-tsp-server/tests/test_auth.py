"""P1 认证接口测试（覆盖 PRD 第 12 节验收标准中的认证部分）。"""

import pytest
from fastapi import HTTPException

from app.db.repo import repo
from app.models.entities import STATUS_DISABLED


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


# ---------------- 登录 ----------------


def test_login_success(seeded, test_password):
    r = post(seeded, "/auth/login", {"username": "student01", "password": test_password})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["role"] == "student"
    assert "password_hash" not in str(body)  # 绝不能外泄


def test_login_wrong_password(seeded, test_password):
    r = post(seeded, "/auth/login", {"username": "student01", "password": "wrong"})
    assert r.status_code == 400
    assert r.json()["code"] == 400


def test_login_unknown_user(seeded):
    r = post(seeded, "/auth/login", {"username": "nobody", "password": "x"})
    assert r.status_code == 400


def test_login_disabled_user(seeded, test_password):
    """被禁用用户登录返回 403（PRD 5.1）。"""
    repo.get_user_by_username("student01").status = STATUS_DISABLED
    r = post(seeded, "/auth/login", {"username": "student01", "password": test_password})
    assert r.status_code == 403
    assert r.json()["code"] == 403


def test_admin_first_login_must_change_password(seeded):
    """admin 首登返回 must_change_password（PRD 5.1）。"""
    from app.config import settings

    # ADMIN_INIT_PASSWORD 未设置时 admin 密码随机，改用种子中的固定密码重置
    user = repo.get_user_by_username("admin")
    from app.utils.security import hash_password

    user.password_hash = hash_password("adminpass123")

    r = post(seeded, "/auth/login", {"username": "admin", "password": "adminpass123"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["must_change_password"] is True
    assert settings.jwt_expire_days == 7


# ---------------- /auth/me ----------------


def test_me_requires_token(seeded):
    r = post(seeded, "/auth/me")
    assert r.status_code == 401


def test_me_returns_current_user(seeded, test_password):
    token = post(seeded, "/auth/login", {"username": "teacher01", "password": test_password}).json()["data"]["token"]
    r = post(seeded, "/auth/me", token=token)
    assert r.status_code == 200
    assert r.json()["data"]["user"]["username"] == "teacher01"


def test_disabled_user_token_invalidated_immediately(seeded, test_password):
    """禁用后已有 JWT 立即失效（PRD 3.3）—— 依赖每次查库校验 status。"""
    token = post(seeded, "/auth/login", {"username": "student01", "password": test_password}).json()["data"]["token"]

    # 禁用前可用
    assert post(seeded, "/auth/me", token=token).status_code == 200

    repo.get_user_by_username("student01").status = STATUS_DISABLED
    # 禁用后同一 token 立即 403
    r = post(seeded, "/auth/me", token=token)
    assert r.status_code == 403


def test_invalid_token_rejected(seeded):
    r = post(seeded, "/auth/me", token="not-a-real-token")
    assert r.status_code == 401


# ---------------- 注册 ----------------


def test_register_student(client):
    r = post(client, "/auth/register", {"username": "newstu", "password": "pass123", "role": "student"})
    assert r.status_code == 200
    user = r.json()["data"]["user"]
    assert user["bind_code"]  # 学生自动生成绑定码


def test_register_duplicate_username(client):
    body = {"username": "dupuser", "password": "pass123", "role": "student"}
    assert post(client, "/auth/register", body).status_code == 200
    r = post(client, "/auth/register", body)
    assert r.status_code == 400
    assert "已存在" in r.json()["message"]


def test_register_admin_not_allowed(client):
    """admin 不开放注册（PRD 5.1）。"""
    r = post(client, "/auth/register", {"username": "eviladmin", "password": "pass123", "role": "admin"})
    assert r.status_code == 400
    assert "admin 不开放注册" in r.json()["message"]


def test_register_short_password(client):
    r = post(client, "/auth/register", {"username": "shortpw", "password": "123", "role": "student"})
    assert r.status_code == 400


# ---------------- 老师邀请码 ----------------


def test_register_teacher_without_invite_code_fails(client):
    r = post(client, "/auth/register", {"username": "teacherx", "password": "pass123", "role": "teacher"})
    assert r.status_code == 400
    assert "邀请码" in r.json()["message"]


def test_register_teacher_with_invalid_invite_code_fails(client):
    r = post(
        client,
        "/auth/register",
        {"username": "teacherx", "password": "pass123", "role": "teacher", "teacher_invite_code": "BADCODE"},
    )
    assert r.status_code == 400
    assert "不存在" in r.json()["message"]


def test_register_teacher_with_valid_invite_code(seeded, invite_code):
    r = post(
        seeded,
        "/auth/register",
        {"username": "teacher99", "password": "pass123", "role": "teacher", "teacher_invite_code": invite_code},
    )
    assert r.status_code == 200
    assert r.json()["data"]["user"]["role"] == "teacher"


def test_invite_code_is_single_use(seeded, invite_code):
    """一码一用（PRD 5.1、第 12 节验收）。"""
    body = {"username": "teacher99", "password": "pass123", "role": "teacher", "teacher_invite_code": invite_code}
    assert post(seeded, "/auth/register", body).status_code == 200

    # 第二次使用同一码应失败
    body2 = dict(body, username="teacher98")
    r = post(seeded, "/auth/register", body2)
    assert r.status_code == 400
    assert "不可用" in r.json()["message"]


def test_expired_invite_code_rejected(client):
    from datetime import datetime, timedelta

    from app.models.entities import User

    client  # noqa: B018 - 使用夹具
    repo.add_user(User(id=0, username="admin2", password_hash="x", role="admin"))
    repo.add_invite_code(
        code="EXPIRED1",
        created_by=1,
        expire_at=datetime.now() - timedelta(days=1),
    )

    r = post(
        client,
        "/auth/register",
        {"username": "teacherexp", "password": "pass123", "role": "teacher", "teacher_invite_code": "EXPIRED1"},
    )
    assert r.status_code == 400
    assert "过期" in r.json()["message"]


def test_revoked_invite_code_rejected(client):
    from app.models.entities import User

    repo.add_user(User(id=0, username="admin3", password_hash="x", role="admin"))
    invite = repo.add_invite_code(code="REVOKED1", created_by=1)
    invite.status = "revoked"

    r = post(
        client,
        "/auth/register",
        {"username": "teacherrev", "password": "pass123", "role": "teacher", "teacher_invite_code": "REVOKED1"},
    )
    assert r.status_code == 400


# ---------------- 修改密码 ----------------


def test_change_password_success(seeded, test_password):
    token = post(seeded, "/auth/login", {"username": "student01", "password": test_password}).json()["data"]["token"]
    r = post(
        seeded,
        "/auth/change-password",
        {"old_password": test_password, "new_password": "newpass456"},
        token=token,
    )
    assert r.status_code == 200
    # 新密码可登录
    assert post(seeded, "/auth/login", {"username": "student01", "password": "newpass456"}).status_code == 200


def test_change_password_wrong_old(seeded, test_password):
    token = post(seeded, "/auth/login", {"username": "student01", "password": test_password}).json()["data"]["token"]
    r = post(
        seeded,
        "/auth/change-password",
        {"old_password": "wrong", "new_password": "newpass456"},
        token=token,
    )
    assert r.status_code == 400


def test_change_password_same_as_old(seeded, test_password):
    token = post(seeded, "/auth/login", {"username": "student01", "password": test_password}).json()["data"]["token"]
    r = post(
        seeded,
        "/auth/change-password",
        {"old_password": test_password, "new_password": test_password},
        token=token,
    )
    assert r.status_code == 400


# ---------------- 权限依赖 ----------------


def test_role_dependency_blocks_wrong_role(seeded, test_password):
    """require_roles 拦截角色不符的请求（PRD 8）。"""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.utils.deps import require_roles
    from app.utils.response import ok

    test_app = FastAPI()

    @test_app.post("/admin-only")
    async def admin_only(user=Depends(require_roles("admin"))):
        return ok({"role": user.role})

    tc = TestClient(test_app, raise_server_exceptions=False)
    token = post(seeded, "/auth/login", {"username": "teacher01", "password": test_password}).json()["data"]["token"]
    r = tc.post("/admin-only", json={}, headers={"Authorization": f"Bearer {token}"})
    # 临时 app 未注册统一异常处理器，这里只校验状态码与 detail 内容
    assert r.status_code == 403
    assert "admin" in r.json()["detail"]["message"]


def test_require_admin_blocks_non_admin(seeded, test_password):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.utils.deps import require_admin
    from app.utils.response import ok

    test_app = FastAPI()

    @test_app.post("/admin-only")
    async def admin_only(user=Depends(require_admin)):
        return ok({"role": user.role})

    tc = TestClient(test_app)
    token = post(seeded, "/auth/login", {"username": "teacher01", "password": test_password}).json()["data"]["token"]
    r = tc.post("/admin-only", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_require_admin_allows_admin(seeded):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.utils.deps import require_admin
    from app.utils.response import ok
    from app.utils.security import hash_password

    test_app = FastAPI()

    @test_app.post("/admin-only")
    async def admin_only(user=Depends(require_admin)):
        return ok({"role": user.role})

    user = repo.get_user_by_username("admin")
    user.password_hash = hash_password("adminpass123")
    user.must_change_password = False  # 已改密，放行业务接口

    tc = TestClient(test_app)
    token = post(seeded, "/auth/login", {"username": "admin", "password": "adminpass123"}).json()["data"]["token"]
    r = tc.post("/admin-only", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["role"] == "admin"


def test_admin_must_change_password_blocks_other_apis(seeded):
    """admin 未改密前访问业务接口 403（PRD 5.1）。"""
    import asyncio

    from app.utils.deps import get_verified_user
    from app.utils.security import hash_password

    user = repo.get_user_by_username("admin")
    user.password_hash = hash_password("adminpass123")
    user.must_change_password = True

    token = post(seeded, "/auth/login", {"username": "admin", "password": "adminpass123"}).json()["data"]["token"]

    async def call():
        return await get_verified_user(authorization=f"Bearer {token}")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(call())
    assert exc_info.value.status_code == 403


# ---------------- 响应格式 ----------------


def test_health_format(seeded):
    """统一响应格式（PRD 3.1）。"""
    r = seeded.post("/health")
    body = r.json()
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 0