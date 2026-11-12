"""课后阅读接口（PRD 5.5）。

**发布**：老师 / admin 均可发布（`created_role` 区分）

**阅读计时与防挂机**
- 进入页面计时，失焦暂停（由客户端不上报实现）
- 每 30 秒心跳上报，后端校验间隔 30s±10s，异常不计时
- 滚动到底标记读完

**积分**（读规则表）
- 每分钟 +1，单篇上限 10，日上限 30
- 读完 +5，单篇 1 次
"""

import secrets
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import (
    ARTICLE_HIDDEN,
    ARTICLE_PUBLISHED,
    POINT_TYPE_READING,
    ROLE_ADMIN,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from app.models.entities import Article, ReadingRecord, User
from app.services import document_service
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok
from app.utils.upload import save_bytes

router = APIRouter()
article_router = APIRouter(prefix="/articles", tags=["阅读"])
parent_articles_router = APIRouter(prefix="/parent/articles", tags=["家长阅读"])

# 心跳间隔：期望 30 秒，允许 ±10 秒浮动（PRD 5.5）
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TOLERANCE = 10


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _student_name(u: User | None) -> str | None:
    """学生展示名：优先昵称，回落用户名，都没有则返回 None。"""
    if u is None:
        return None
    return u.nickname or u.username


def _article_to_dict(a: Article, with_content: bool = True) -> dict:
    d = {
        "id": a.id,
        "author_id": a.author_id,
        "created_role": a.created_role,
        "title": a.title,
        "cover": a.cover,
        "status": a.status,
        "file_url": a.file_url,
        "file_name": a.file_name,
        "file_type": a.file_type,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    if with_content:
        d["content"] = a.content
    return d


# ---------------- 出入参 ----------------


class ArticleCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    cover: str | None = Field(None, max_length=255)


class ArticleListRequest(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class ArticleDetailRequest(BaseModel):
    article_id: int


class ParentArticleListRequest(ArticleListRequest):
    student_id: int


class ParentArticleDetailRequest(ArticleDetailRequest):
    student_id: int


def _require_bound_student(repo: Repo, user: User, student_id: int) -> None:
    if user.role != ROLE_PARENT:
        raise _forbidden("仅家长可使用此接口")
    if not repo.get_parent_student(user.id, student_id):
        raise _forbidden("只能操作自己绑定的孩子")
    child = repo.get_user_by_id(student_id)
    if not child or child.role != ROLE_STUDENT:
        raise _not_found("学生不存在")


class HeartbeatRequest(BaseModel):
    article_id: int
    seconds: int = Field(..., ge=0, le=300)  # 本次心跳累计的阅读秒数


class ArticleIdRequest(BaseModel):
    article_id: int


# ---------------- 接口 ----------------


@article_router.post("/create")
async def create_article(
    req: ArticleCreateRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """发布文章 —— teacher / admin 均可（PRD 5.5）。"""
    if user.role not in (ROLE_TEACHER, ROLE_ADMIN):
        raise _forbidden("仅老师或管理员可发布文章")

    art = Repo(db).add_article(
        Article(
            author_id=user.id,
            created_role=user.role,  # 区分发布来源（PRD 5.5）
            title=req.title.strip(),
            content=req.content,
            cover=req.cover,
            status=ARTICLE_PUBLISHED,
        )
    )
    db.commit()
    return ok({"article": _article_to_dict(art)})


@article_router.post("/create-file")
async def create_article_file(
    title: str = Form(...),
    cover: str | None = Form(None),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """发布文章 —— teacher / admin 均可；支持纯文本 / PDF / word（PRD 5.5、迭代 v2.1）。

    - 上传 PDF / word：服务端抽取正文入库，学生端读到的仍是**文本**（天然只读）
    - 不传文件：直接使用 content 纯文本
    """
    if user.role not in (ROLE_TEACHER, ROLE_ADMIN):
        raise _forbidden("仅老师或管理员可发布文章")

    title = (title or "").strip()
    if not title:
        raise _bad_request("请填写标题")

    text = (content or "").strip()
    file_url = None
    file_name = None
    file_type = None

    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower().lstrip(".")
        if suffix not in settings.article_allowed_extension_list:
            raise _bad_request(
                f"不支持的文件类型：{suffix or '未知'}，"
                f"仅允许 {', '.join(settings.article_allowed_extension_list)}"
            )
        data = await file.read()
        if len(data) > settings.article_max_upload_mb * 1024 * 1024:
            raise _bad_request(f"文件超过 {settings.article_max_upload_mb}MB 限制")

        try:
            text = document_service.extract_text(data, suffix)
        except document_service.DocumentParseError as exc:
            raise _bad_request(str(exc))

        file_url = save_bytes(
            data,
            file.filename,
            allowed=settings.article_allowed_extension_list,
            max_mb=settings.article_max_upload_mb,
        )
        file_name = Path(file.filename).name
        file_type = suffix

    if not text:
        raise _bad_request("请填写正文或上传文章文件")

    art = Repo(db).add_article(
        Article(
            author_id=user.id,
            created_role=user.role,
            title=title,
            content=text,
            cover=cover,
            status=ARTICLE_PUBLISHED,
            file_url=file_url,
            file_name=file_name,
            file_type=file_type,
        )
    )
    db.commit()
    return ok({"article": _article_to_dict(art)})


@article_router.post("/list")
async def list_articles(
    req: ArticleListRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """文章列表 —— 学生端仅见 published（PRD 5.5、5.8.4）。"""
    status = ARTICLE_PUBLISHED if user.role in (ROLE_STUDENT, ROLE_PARENT) else None
    items, total = Repo(db).list_articles_paged(
        status=status, page=req.page, size=req.size
    )
    return ok({
        # 列表不返回正文，避免流量浪费
        "list": [_article_to_dict(a, with_content=False) for a in items],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@article_router.post("/detail")
async def article_detail(
    req: ArticleDetailRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """文章详情。学生端不可看 hidden（PRD 5.5）。"""
    art = Repo(db).get_article_by_id(req.article_id)
    if not art:
        raise _not_found("文章不存在")

    if user.role in (ROLE_STUDENT, ROLE_PARENT) and art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")

    data = _article_to_dict(art)
    if user.role == ROLE_STUDENT:
        rec = Repo(db).get_reading_record(art.id, user.id, date.today())
        data["my_record"] = {
            "duration_seconds": rec.duration_seconds if rec else 0,
            "finished": bool(rec.finished) if rec else False,
            "points": rec.points if rec else 0,
        } if rec else None
    return ok({"article": data})


@article_router.post("/heartbeat")
def heartbeat(
    req: HeartbeatRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """阅读心跳上报（PRD 5.5）。

    后端校验间隔 30s±10s：客户端声明的 `seconds` 若超出该区间，
    判定为挂机/篡改，**本次不计时、不计分**。
    """
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可阅读计时")

    repo = Repo(db)
    art = repo.get_article_by_id(req.article_id, for_update=True)
    if not art:
        raise _not_found("文章不存在")
    if art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")

    # 间隔校验：单次心跳应在 30s±10s 内
    upper = HEARTBEAT_INTERVAL + HEARTBEAT_TOLERANCE
    suspicious = req.seconds > upper

    # 先锁学生，后查/插阅读记录，避免子表外键锁升级及旧快照。
    student = repo.get_user_by_id_for_update(student.id)
    today = date.today()
    rec = repo.get_reading_record(art.id, student.id, today, for_update=True)
    if not rec:
        rec = repo.add_reading_record(
            ReadingRecord(
                article_id=art.id,
                student_id=student.id,
                read_date=today,
                duration_seconds=0,
                finished=False,
                points=0,
            )
        )

    if suspicious:
        # 异常间隔：只记录不计时（PRD 5.5、第 12 节验收）
        db.commit()
        return ok({
            "accepted": False,
            "reason": f"心跳间隔异常（{req.seconds}s 超出 {upper}s），本次不计分",
            "duration_seconds": rec.duration_seconds,
            "points": rec.points,
        })

    rec.duration_seconds += req.seconds

    from app.services import point_service

    gained = 0
    # 每满 1 分钟发 1 分（reading_per_minute）
    new_minutes = rec.duration_seconds // 60 - (rec.duration_seconds - req.seconds) // 60
    if new_minutes > 0:
        gained = _award_reading_points(
            db, student, art, rec, new_minutes, today
        )

    db.commit()
    db.refresh(rec)

    return ok({
        "accepted": True,
        "duration_seconds": rec.duration_seconds,
        "points": rec.points,
        "points_gained": gained,
        "finished": bool(rec.finished),
    })


def _award_reading_points(
    db: Session,
    student: User,
    art: Article,
    rec: ReadingRecord,
    minutes: int,
    today: date,
) -> int:
    """按阅读时长发放积分。

    PRD 5.5：每分钟 +1，**单篇上限 10，日上限 30**。
    两个上限都在 extra_config / daily_limit 中，按已发额度截断。
    """
    from app.services import point_service
    from app.services.point_rule_service import rule_service

    rule = rule_service.get(db, "reading_per_minute")
    if rule is None or not rule.enabled:
        return 0

    # 单篇上限（extra_config.single_article_limit，默认 10）
    per_minute = rule.points or 1
    single_limit = rule_service.get_extra(
        db, "reading_per_minute", "single_article_limit", default=10
    )

    # 该篇今日已发放的阅读积分（跨天记录按 read_date 限定）
    article_gained = point_service.sum_points_by_type_on(db, student.id, POINT_TYPE_READING, today)
    # 简化为：该生今日阅读总额已达单篇上限则不再发
    if article_gained >= single_limit:
        return 0

    want = minutes * per_minute
    room = single_limit - article_gained
    if want > room:
        want = room

    if want <= 0:
        return 0

    return point_service.award(
        db,
        student.id,
        POINT_TYPE_READING,
        "reading_per_minute",
        remark=f"阅读：{art.title}",
        operator_id=student.id,
        enforce_limit=True,  # 日上限 30 生效
    ) or want


@article_router.post("/finish")
def finish_reading(
    req: ArticleIdRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """标记读完（滚动到底触发），读完 +5，单篇 1 次（PRD 5.5）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可阅读")

    repo = Repo(db)
    art = repo.get_article_by_id(req.article_id, for_update=True)
    if not art or art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")

    # 先锁学生，后查/插阅读记录，避免子表外键锁升级及旧快照。
    student = repo.get_user_by_id_for_update(student.id)
    today = date.today()
    rec = repo.get_reading_record(art.id, student.id, today, for_update=True)
    if not rec:
        rec = repo.add_reading_record(
            ReadingRecord(
                article_id=art.id,
                student_id=student.id,
                read_date=today,
                duration_seconds=0,
                finished=False,
                points=0,
            )
        )

    if rec.finished:
        # 已标记读完，单篇只发一次奖励（PRD 5.5）
        db.commit()
        return ok({
            "already_finished": True,
            "points": rec.points,
            "duration_seconds": rec.duration_seconds,
        })

    rec.finished = True

    from app.services import point_service

    bonus = point_service.award(
        db,
        student.id,
        POINT_TYPE_READING,
        "reading_finish",
        remark=f"读完：{art.title}",
        operator_id=student.id,
    )
    rec.points += bonus

    db.commit()
    return ok({
        "already_finished": False,
        "points_gained": bonus,
        "points": rec.points,
        "duration_seconds": rec.duration_seconds,
    })


@article_router.post("/records")
async def article_records(
    req: ArticleIdRequest,
    teacher: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """老师查看本文章的阅读记录（PRD 5.5）。老师仅能看自己的文章。"""
    if teacher.role not in (ROLE_TEACHER, ROLE_ADMIN):
        raise _forbidden("仅老师或管理员可查看阅读记录")

    repo = Repo(db)
    art = repo.get_article_by_id(req.article_id)
    if not art:
        raise _not_found("文章不存在")
    # 老师仅能管自己的文章（PRD 5.5、第 8 节）
    if teacher.role == ROLE_TEACHER and art.author_id != teacher.id:
        raise _forbidden("只能查看自己发布的文章")

    records = repo.list_reading_records(art.id)
    students = repo.list_users_by_ids(sorted({r.student_id for r in records}))
    return ok({
        "article": _article_to_dict(art, with_content=False),
        "records": [
            {
                "student_id": r.student_id,
                "student_name": _student_name(students.get(r.student_id)),
                "duration_seconds": r.duration_seconds,
                "finished": bool(r.finished),
                "points": r.points,
                "read_date": r.read_date.isoformat() if r.read_date else None,
            }
            for r in records
        ],
        "stats": repo.article_read_stats(art.id),
    })


@article_router.post("/delete")
def delete_article(
    req: ArticleIdRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """删除文章 —— 老师仅能删自己的；admin 可删任意（PRD 5.5、5.8.4）。"""
    repo = Repo(db)
    art = repo.get_article_by_id(req.article_id, for_update=True)
    if not art:
        raise _not_found("文章不存在")

    if user.role == ROLE_TEACHER and art.author_id != user.id:
        raise _forbidden("只能删除自己发布的文章")
    if user.role not in (ROLE_TEACHER, ROLE_ADMIN):
        raise _forbidden("无权限删除文章")

    art.deleted_at = datetime.now()
    db.commit()
    return ok({"deleted_id": req.article_id})


@article_router.post("/export-pdf")
def export_article_pdf(
    req: ArticleIdRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """导出文章为 PDF（PRD 5.5、迭代 v2.1）。

    服务端用 reportlab 排版（中文字体 STSong-Light），生成的 PDF 存 uploads，
    返回相对路径供客户端下载/预览。学生端仅可导出 published 文章。
    """
    repo = Repo(db)
    art = repo.get_article_by_id(req.article_id, for_update=True)
    if not art:
        raise _not_found("文章不存在")
    if user.role == ROLE_STUDENT and art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")
    if user.role not in (ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN):
        raise _forbidden("无权限导出文章")

    pdf_bytes = document_service.render_text_to_pdf(art.title, art.content)
    file_url = save_bytes(
        pdf_bytes,
        f"{art.id}_{secrets.token_hex(4)}.pdf",
        allowed=["pdf"],
        max_mb=settings.article_max_upload_mb,
    )
    return ok({
        "file_url": file_url,
        "file_name": f"{art.title}.pdf",
        "size_bytes": len(pdf_bytes),
    })


@parent_articles_router.post("/list")
def parent_list_articles(
    req: ParentArticleListRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    repo = Repo(db)
    _require_bound_student(repo, user, req.student_id)
    items, total = repo.list_articles_paged(
        status=ARTICLE_PUBLISHED, page=req.page, size=req.size
    )
    return ok({
        "list": [_article_to_dict(a, with_content=False) for a in items],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@parent_articles_router.post("/detail")
def parent_article_detail(
    req: ParentArticleDetailRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    repo = Repo(db)
    _require_bound_student(repo, user, req.student_id)
    art = repo.get_article_by_id(req.article_id)
    if not art or art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")
    return ok({"article": _article_to_dict(art)})


@parent_articles_router.post("/download", response_class=StreamingResponse)
def parent_download_article(
    req: ParentArticleDetailRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """家长下载已发布文章，PDF 仅在内存中生成。"""
    repo = Repo(db)
    _require_bound_student(repo, user, req.student_id)
    art = repo.get_article_by_id(req.article_id)
    if not art or art.status != ARTICLE_PUBLISHED:
        raise _not_found("文章不存在")

    pdf_bytes = document_service.render_text_to_pdf(art.title, art.content)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="article-{art.id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


router.include_router(article_router)
router.include_router(parent_articles_router)