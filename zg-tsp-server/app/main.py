"""zg-tsp-server 应用入口。

本模块可独立启动，不依赖任何其他模块：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routers import (
    admin,
    admin_idioms,
    articles,
    auth,
    checkin,
    classes,
    games,
    homework,
    parent,
    point_rules_admin,
    points,
)
from app.utils.response import (
    CODE_BAD_REQUEST,
    CODE_SERVER_ERROR,
    fail,
    ok,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时确保表存在。

    种子数据由 `python -m app.seed.initial_data` 显式执行（PRD 10.4），
    不在启动时自动跑，避免生产环境意外写入默认账号。
    """
    from app.db.session import engine
    from app.models.entities import Base

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

# 上传文件访问（迭代 v2.1：此前 /uploads/<name> 无对应路由，作业附件实际 404）
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


# --- 统一异常响应（PRD 3.1）---


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTPException 的 detail 已按 {code, message} 结构构造。"""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content=fail(detail["code"], detail["message"]))
    return JSONResponse(status_code=exc.status_code, content=fail(exc.status_code, str(detail)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败 → 400，附带首条错误信息。"""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "参数错误")
    message = f"{field}: {msg}" if field else msg
    return JSONResponse(status_code=400, content=fail(CODE_BAD_REQUEST, message))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("未处理异常")
    return JSONResponse(status_code=500, content=fail(CODE_SERVER_ERROR, "服务端错误"))


# --- 路由 ---


@app.post("/health")
async def health():
    """健康检查：供 Docker HEALTHCHECK 与客户端可用性探测使用。"""
    return ok({"status": "ok", "env": settings.env})


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(point_rules_admin.router)
app.include_router(classes.router)
app.include_router(homework.router)
app.include_router(checkin.router)
app.include_router(points.router)
app.include_router(parent.router)
app.include_router(articles.router)
app.include_router(games.router)
app.include_router(admin_idioms.router)