"""上传文件保存（PRD 10.1）。

作业与文章共用同一套「白名单 + 大小限制 + 落盘」逻辑，
调用方通过 `allowed` / `max_mb` 传入各自的限制。
"""

import secrets
from pathlib import Path

from fastapi import HTTPException

from app.config import settings
from app.utils.response import CODE_BAD_REQUEST


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def save_bytes(
    data: bytes,
    filename: str,
    *,
    allowed: list[str],
    max_mb: int,
) -> str:
    """校验并保存字节流，返回相对 URL（`/uploads/<name>`）。

    扩展名白名单与大小限制由调用方决定：
    - 作业：settings.allowed_extension_list（jpg/jpeg/png/pdf）
    - 文章：settings.article_allowed_extension_list（pdf/docx）
    """
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    if suffix not in allowed:
        raise _bad_request(f"不支持的文件类型：{suffix or '未知'}，仅允许 {', '.join(allowed)}")

    limit = max_mb * 1024 * 1024
    if len(data) > limit:
        raise _bad_request(f"文件超过 {max_mb}MB 限制")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}_{Path(filename or 'upload').name}"
    (upload_dir / name).write_bytes(data)
    return f"/uploads/{name}"


async def save_upload(
    file,
    *,
    allowed: list[str],
    max_mb: int,
) -> str:
    """保存 `UploadFile`，返回相对 URL。"""
    return save_bytes(
        await file.read(),
        file.filename or "upload",
        allowed=allowed,
        max_mb=max_mb,
    )
