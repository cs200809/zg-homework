"""统一响应格式（见 PRD 3.1）。

    {"code": 0, "message": "ok", "data": {}}

错误码：0 成功 / 400 参数错误 / 401 未认证 / 403 无权限 /
        404 不存在 / 429 限流 / 500 服务端错误
"""

from typing import Any

# 业务错误码
CODE_OK = 0
CODE_BAD_REQUEST = 400
CODE_UNAUTHORIZED = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_RATE_LIMIT = 429
CODE_SERVER_ERROR = 500


def ok(data: Any = None, message: str = "ok") -> dict:
    """成功响应。"""
    return {"code": CODE_OK, "message": message, "data": data if data is not None else {}}


def fail(code: int, message: str, data: Any = None) -> dict:
    """失败响应。"""
    return {
        "code": code,
        "message": message,
        "data": data if data is not None else {},
    }