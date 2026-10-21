"""密码哈希与 JWT 工具（PRD 3.3、5.1）。"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt 哈希；passlib 1.7.4 需显式指定 rounds 以规避 bcrypt 4.x 读取警告
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    """bcrypt 加密。"""
    return pwd_context.hash(password)


def verify_password(plain: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    try:
        return pwd_context.verify(plain, password_hash)
    except ValueError:
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