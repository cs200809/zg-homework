"""pytest 夹具。

**测试库约定：只增不删**

测试直接跑在开发库 `zg_tsp` 上。为保证用例之间互不干扰又不破坏已有数据：

- 每个用例使用**带随机后缀的唯一用户名**（如 `t_a1b2c3_stu01`），天然不冲突
- 只做 INSERT / UPDATE，**从不 TRUNCATE、从不 DELETE**
- 测试数据会残留在库里；这是刻意接受的代价

因此用例可以断言「新增的用户确实存在于库中」，
也能覆盖「跨会话可见」这类需要真实提交的逻辑。

如需干净起点，可手动执行：
    python -m app.seed.initial_data --reset
注意该命令会删表重建，且会打印新的随机 admin 密码。
"""

import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 测试库可通过环境变量覆盖，默认沿用 app.config 的开发库
_override = os.environ.get("DATABASE_URL")
if _override:
    os.environ["DATABASE_URL"] = _override

from app.config import settings  # noqa: E402
from app.db.repo import Repo  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.constants import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import Base, User  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

TEST_PASSWORD = "test123456"


@pytest.fixture(scope="session", autouse=True)
def _ensure_tables():
    """确保表已建（只建不删）。"""
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    """独立会话。测试用例请自行 commit 或依赖 rollback。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def refresh(db):
    """确保读到其他会话（HTTP 请求）刚提交的数据。

    MySQL 默认 REPEATABLE READ：事务一旦开始就固定快照，之后 expire_all()
    重新查询仍读到旧数据。因此必须先结束当前事务（rollback），再清掉会话内
    对象缓存，让下一次查询开新事务取最新数据。
    """

    def _refresh() -> None:
        db.rollback()  # 结束快照事务
        db.expire_all()  # 清掉会话内对象缓存

    return _refresh


@pytest.fixture
def uid():
    """本用例的唯一标识后缀，用于生成不冲突的用户名/邀请码。"""
    return secrets.token_hex(3)


@pytest.fixture
def uname(uid):
    """生成唯一用户名工厂：uname('stu') -> 't_a1b2c3_stu'（≤20 字符）。

    每次调用都会换一个新后缀，因此同一用例内循环创建也不会撞唯一索引。
    """
    counter = 0
    base = uid

    def _make(tag: str) -> str:
        nonlocal counter
        counter += 1
        return f"t{base}{counter:x}_{tag}"[:20]

    return _make


@pytest.fixture
def client(db):
    """TestClient。lifespan 会执行种子，已存在则跳过。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(db, uname):
    """创建测试用户并返回 (User, 明文密码)。"""

    def _make(role: str, tag: str = "usr", **kwargs):
        password = kwargs.pop("password", TEST_PASSWORD)
        user = User(
            username=uname(tag),
            password_hash=hash_password(password),
            role=role,
            nickname=kwargs.pop("nickname", "测试用户"),
            **kwargs,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, password

    return _make


@pytest.fixture
def login(client):
    """登录并返回 token。

    接受两种入参形式：
        login("username")
        login(user, password)      # make_user 的返回值直接展开
        login(user)                 # user 对象，自动取其密码
    """

    def _login(user_or_name, password: str = TEST_PASSWORD) -> str:
        username = getattr(user_or_name, "username", user_or_name)
        r = client.post("/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, f"登录失败 {username}: {r.text}"
        return r.json()["data"]["token"]

    return _login


@pytest.fixture
def admin_token(client, db):
    """以 admin 身份登录（用于需 admin 权限的用例）。

    若 admin 尚不存在则创建；密码固定为 ADMIN_TEST_PASSWORD。
    """
    repo = Repo(db)
    admin = repo.get_user_by_username("admin")
    if admin is None:
        admin = repo.add_user(
            User(
                username="admin",
                password_hash=hash_password("admin_init_pass"),
                role=ROLE_ADMIN,
                nickname="超级管理员",
                must_change_password=True,
            )
        )
        db.commit()

    password = "admin_test_pass"
    admin.password_hash = hash_password(password)
    admin.must_change_password = False
    admin.status = "active"
    db.commit()

    r = client.post("/auth/login", json={"username": "admin", "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


@pytest.fixture
def set_user_status(db):
    """修改用户状态（模拟 admin 禁用/启用）。"""

    def _set(user_id: int, status: str) -> None:
        user = Repo(db).get_user_by_id(user_id)
        user.status = status
        db.commit()

    return _set


@pytest.fixture
def make_invite(db, uname):
    """创建老师邀请码，返回 (code, created_by_user_id)。"""

    def _make(tag: str = "inv", expire_at=None, status: str = "unused"):
        admin = Repo(db).get_user_by_username("admin")
        if admin is None:
            admin = repo.add_user(
                User(username="admin", password_hash="x", role=ROLE_ADMIN)
            )
            db.commit()
        code = uname(tag).upper()[:12]
        invite = Repo(db).add_invite_code(code=code, created_by=admin.id, expire_at=expire_at)
        invite.status = status
        db.commit()
        return code

    return _make

# ==================== P2 夹具 ====================


@pytest.fixture
def make_class(db, make_user):
    """创建班级（含班主任），返回 (Class, teacher, teacher_password)。"""

    def _make(name: str = "测试班", teacher=None):
        from app.models.entities import Class

        if teacher is None:
            teacher, pw = make_user(ROLE_TEACHER, "cls")
        else:
            pw = None

        import secrets
        from app.db.repo import Repo

        repo = Repo(db)
        code = f"C{secrets.token_hex(3).upper()}"[:8]
        klass = repo.add_class(
            Class(name=name, invite_code=code, teacher_id=teacher.id)
        )
        db.commit()
        return klass, teacher, pw

    return _make


@pytest.fixture
def enroll(db):
    """把学生加入班级。"""

    def _enroll(student, klass):
        student.class_id = klass.id
        db.commit()
        return student

    return _enroll
