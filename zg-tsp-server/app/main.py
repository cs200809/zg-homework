"""zg-tsp-server 应用入口。

本模块可独立启动，不依赖任何其他模块：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.utils.response import ok

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.post("/health")
async def health():
    """健康检查：供 Docker HEALTHCHECK 与客户端可用性探测使用。"""
    return ok({"status": "ok", "env": settings.env})


# 各业务路由在对应 Phase 挂载：
# app.include_router(auth.router, prefix="/auth", tags=["认证"])
# app.include_router(classes.router, prefix="/classes", tags=["班级"])
# app.include_router(homework.router, prefix="/homework", tags=["作业"])
# app.include_router(checkin.router, prefix="/checkin", tags=["签到"])
# app.include_router(points.router, prefix="/points", tags=["积分"])
# app.include_router(articles.router, prefix="/articles", tags=["阅读"])
# app.include_router(games.router, prefix="/games", tags=["游戏"])
# app.include_router(parent.router, prefix="/parent", tags=["家长"])
# app.include_router(admin.router, prefix="/admin", tags=["管理员"])