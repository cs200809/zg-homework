"""权限依赖（PRD 3.3、8）。

关键规则：
- JWT 放 Header，依赖中**查库校验 status=active**，禁用后立即失效
- admin 未改密前访问业务接口返回 403
- 角色校验：require_roles(...) / require_admin

注意：权限依赖每次请求都会查库 —— 这是「禁用立即生效」的实现基础，不要缓存。
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import ROLE_ADMIN, STATUS_ACTIVE
from app.models.entities import User
from app.utils.response import CODE_FORBIDDEN, CODE_UNAUTHORIZED
from app.utils.security import decode_access_token


def _unauthorized(message: str = "未认证或登录已过期") -> HTTPException:
    return HTTPException(status_code=401, detail={"code": CODE_UNAUTHORIZED, "message": message})


def _forbidden(message: str = "无权限") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer token 并返回当前用户。

    每次请求都查库，因此后台禁用用户后其已有 JWT 立即失效（PRD 3.3）。
    """
    if not authorization:
        raise _unauthorized("缺少 Authorization 头")

    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized("Authorization 格式应为 Bearer <token>")

    payload = decode_access_token(parts[1].strip())
    if not payload:
        raise _unauthorized("token 无效或已过期")

    user = Repo(db).get_user_by_id(payload.get("user_id"))
    if not user:
        raise _unauthorized("用户不存在")

    if user.status != STATUS_ACTIVE:
        raise _forbidden("账号已被禁用")

    return user


def get_verified_user(user: User = Depends(get_current_user)) -> User:
    """在 get_current_user 基础上，拦截未改密的 admin（PRD 5.1）。"""
    if user.must_change_password:
        raise _forbidden("请先修改初始密码")
    return user


def require_roles(*roles: str):
    """生成角色校验依赖。内部使用 get_verified_user，
    因此同样会拦截「未改密的 admin」。"""

    def _check(user: User = Depends(get_verified_user)) -> User:
        if user.role not in roles:
            raise _forbidden(f"需要 {', '.join(roles)} 角色")
        return user

    return _check


def require_admin(user: User = Depends(get_verified_user)) -> User:
    """admin 专用依赖。"""
    if user.role != ROLE_ADMIN:
        raise _forbidden("需要 admin 角色")
    return user