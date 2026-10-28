"""密码重置工具测试（app.utils.reset_password）。

背景：admin 种子密码是随机生成、仅打印一次的明文，README 里记录的密码在
首登改密后就失效了，导致按文档登录必然 400。需要一个可重复执行的重置入口。
"""

import pytest

from app.db.repo import Repo
from app.utils.reset_password import PasswordResetError, reset_password
from app.utils.security import verify_password


def test_reset_password_changes_hash(db, make_user):
    """重置后新密码可校验通过。"""
    user, _ = make_user("student", "rst")
    original_hash = user.password_hash

    reset_password(db, user.username, "newpass123")

    db.expire_all()
    updated = Repo(db).get_user_by_username(user.username)
    assert updated.password_hash != original_hash
    assert verify_password("newpass123", updated.password_hash) is True


def test_reset_password_sets_must_change_password(db, make_user):
    """重置密码后应强制用户下次登录改密。"""
    user, _ = make_user("student", "rst")

    reset_password(db, user.username, "newpass123")

    db.expire_all()
    updated = Repo(db).get_user_by_username(user.username)
    assert updated.must_change_password is True


def test_reset_password_reactivates_disabled_user(db, make_user):
    """重置密码应同时解除禁用状态，否则重置后仍无法登录。"""
    user, _ = make_user("student", "rst")
    user.status = "disabled"
    db.commit()

    reset_password(db, user.username, "newpass123")

    db.expire_all()
    updated = Repo(db).get_user_by_username(user.username)
    assert updated.status == "active"


def test_reset_password_unknown_user_raises(db):
    with pytest.raises(PasswordResetError, match="不存在"):
        reset_password(db, "no_such_user_xyz", "newpass123")


def test_reset_password_too_short_raises(db, make_user):
    """密码过短应被拒绝，避免重置出一个不合规的密码。"""
    user, _ = make_user("student", "rst")
    with pytest.raises(PasswordResetError, match="长度"):
        reset_password(db, user.username, "123")


def test_reset_password_can_reset_admin(db, make_user):
    """admin 同样可重置（首登改密后 README 记录失效的情况）。"""
    user, _ = make_user("admin", "adm")

    reset_password(db, user.username, "adminpass123")

    db.expire_all()
    updated = Repo(db).get_user_by_username(user.username)
    assert verify_password("adminpass123", updated.password_hash) is True
