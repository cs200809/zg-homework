"""密码哈希与 JWT 工具（PRD 3.3、5.1）。

密码哈希直接使用 bcrypt 原生库，不经 passlib：
passlib 1.7.4 读取 bcrypt 版本的方式（`bcrypt.__about__.__version__`）在
bcrypt 4.1+ 已被移除，每次加载 backend 都会打印一段 traceback 告警，
并把版本误记为 '<unknown>'。passlib 官方已于 2020 年归档维护，
故直接依赖 bcrypt 原生 API。

两种实现生成的哈希格式一致（$2b$<cost>$...），存量数据可正常校验。
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt cost factor。12 是目前常用的平衡点（OWASP 建议 10~12）。
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """bcrypt 加密，返回 $2b$ 开头的哈希串。"""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配。

    哈希损坏（非法 base64 / 非法 cost / 空串）时返回 False 而非抛异常，
    避免脏数据把登录接口打成 500。
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # 哈希本身损坏
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """签发 JWT。

    返回 (token, 过期时间戳秒)。有效期 7 天（PRD 3.3）。
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expire.timestamp())


def decode_access_token(token: str) -> dict | None:
    """解析 JWT。失败（过期/签名错误/格式错误）返回 None。"""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None