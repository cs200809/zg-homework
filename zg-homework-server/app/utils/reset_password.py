"""密码重置工具（开发/运维用）。

背景：admin 种子密码是随机生成、仅在种子运行时打印一次的明文，
首登改密后 README 里记录的那个密码就失效了 —— 按文档登录必然 400。
这里提供一个可重复执行的重置入口：

    python -m app.utils.reset_password admin
    python -m app.utils.reset_password admin --password '新密码'
    python -m app.utils.reset_password admin --generate   # 随机生成并打印

重置后账号会被解除禁用状态，并置 must_change_password，
使用户下次登录强制改密。
"""

import argparse
import logging
import secrets
import sys

from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import SessionLocal
from app.models.entities import User
from app.utils.security import hash_password

logger = logging.getLogger(__name__)

# 与 app.schemas.auth 的注册密码长度约束保持一致
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 64


class PasswordResetError(Exception):
    """重置失败（用户不存在、密码不合规等）。"""


def reset_password(
    db: Session,
    username: str,
    new_password: str,
    *,
    reactivate: bool = True,
) -> User:
    """把指定账号的密码重置为 new_password。

    同时：
    - 置 must_change_password=True，让用户下次登录强制改密
    - 默认解除 disabled 状态（否则重置后依然无法登录）

    返回更新后的 User。失败抛 PasswordResetError。
    """
    username = (username or "").strip()
    if not username:
        raise PasswordResetError("用户名不能为空")

    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise PasswordResetError(
            f"新密码长度不足 {MIN_PASSWORD_LENGTH} 位（当前 {len(new_password)} 位）"
        )
    if len(new_password) > MAX_PASSWORD_LENGTH:
        raise PasswordResetError(
            f"新密码长度超过 {MAX_PASSWORD_LENGTH} 位（当前 {len(new_password)} 位）"
        )

    user = Repo(db).get_user_by_username(username)
    if user is None:
        raise PasswordResetError(f"用户不存在：{username}")

    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    if reactivate:
        user.status = "active"
    db.commit()
    db.refresh(user)
    return user


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.utils.reset_password",
        description="重置指定账号的密码（开发/运维用）",
    )
    parser.add_argument("username", help="要重置的用户名")
    parser.add_argument(
        "--password",
        help=f"新密码（至少 {MIN_PASSWORD_LENGTH} 位）；省略则随机生成",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="随机生成新密码并打印（不传 --password 时的默认行为）",
    )
    args = parser.parse_args(argv)

    password = args.password
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    else:
        generated = False

    db = SessionLocal()
    try:
        user = reset_password(db, args.username, password)
    except PasswordResetError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"✓ 已重置 {user.username}（{user.role}）的密码")
    if generated:
        print(f"  新密码：{password}")
        print("  （仅本次显示，请立即登录并修改）")
    print("  该账号下次登录将强制修改密码。")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(_main())
