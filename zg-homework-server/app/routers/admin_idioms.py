"""成语题库管理接口（PRD 5.8.6，决策 4）。

- 批量导入题目（JSON 文件或逐条提交，单次上限 1000 条）
- 导入校验：prompt/answer 非空；同批内 prompt 去重；已存在则跳过或覆盖（mode）
- 干扰项为 JSON 数组，不足时服务端随机补齐
- 列表支持关键词、启用状态筛选、分页
- 单条编辑 / 删除 / 批量删除；写 admin_logs
- 题目 enabled=false 后学生端不再抽到
"""

import json
import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.entities import IdiomQuestion, User
from app.utils.deps import require_admin
from app.utils.response import CODE_BAD_REQUEST, CODE_NOT_FOUND, ok

router = APIRouter(
    prefix="/admin/idioms",
    tags=["成语题库"],
    dependencies=[Depends(require_admin)],
)

MAX_IMPORT_ITEMS = 1000
VALID_MODES = ("skip", "overwrite")


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


# ---------------- 出入参 ----------------


class IdiomItem(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50)
    answer: str = Field(..., min_length=1, max_length=50)
    distractors: list[str] | None = None
    difficulty: str = Field("normal", max_length=10)


class IdiomImportRequest(BaseModel):
    items: list[IdiomItem] = Field(..., min_length=1, max_length=MAX_IMPORT_ITEMS)
    mode: str = Field("skip")  # skip 跳过已存在 / overwrite 覆盖


class IdiomListRequest(BaseModel):
    keyword: str | None = None
    enabled: bool | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class IdiomUpdateRequest(BaseModel):
    question_id: int
    prompt: str | None = Field(None, min_length=1, max_length=50)
    answer: str | None = Field(None, min_length=1, max_length=50)
    distractors: list[str] | None = None
    difficulty: str | None = Field(None, max_length=10)
    enabled: bool | None = None


class IdiomDeleteRequest(BaseModel):
    question_id: int


class IdiomBatchDeleteRequest(BaseModel):
    question_ids: list[int] = Field(..., min_length=1, max_length=1000)


def _to_dict(q: IdiomQuestion) -> dict:
    return {
        "id": q.id,
        "prompt": q.prompt,
        "answer": q.answer,
        "distractors": json.loads(q.distractors) if q.distractors else [],
        "difficulty": q.difficulty,
        "enabled": bool(q.enabled),
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


# ---------------- 接口 ----------------


@router.post("/import")
async def import_idioms(
    req: IdiomImportRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量导入成语题目（PRD 5.8.6）。"""
    if req.mode not in VALID_MODES:
        raise _bad_request(f"mode 必须是 {', '.join(VALID_MODES)} 之一")

    repo = Repo(db)
    success = 0
    skipped = 0
    updated = 0
    seen_in_batch: set[str] = set()
    duplicates_in_batch = 0

    for item in req.items:
        prompt = item.prompt.strip()
        answer = item.answer.strip()

        if not prompt or not answer:
            raise _bad_request("prompt 与 answer 均不能为空")

        # 同批内去重（PRD 5.8.6）
        if prompt in seen_in_batch:
            duplicates_in_batch += 1
            skipped += 1
            continue
        seen_in_batch.add(prompt)

        existing = db.scalar(select(IdiomQuestion).where(IdiomQuestion.prompt == prompt))
        if existing:
            if req.mode == "skip":
                skipped += 1
                continue
            existing.answer = answer
            existing.distractors = (
                json.dumps(item.distractors, ensure_ascii=False) if item.distractors else None
            )
            existing.difficulty = item.difficulty
            existing.created_by = admin.id
            updated += 1
            continue

        db.add(
            IdiomQuestion(
                prompt=prompt,
                answer=answer,
                distractors=(
                    json.dumps(item.distractors, ensure_ascii=False) if item.distractors else None
                ),
                difficulty=item.difficulty,
                created_by=admin.id,
            )
        )
        success += 1

    repo.add_admin_log(
        admin_id=admin.id,
        action="idiom_import",
        target_type="idiom_question",
        detail=f"导入成语题目：新增 {success}、更新 {updated}、跳过 {skipped}（mode={req.mode}）",
    )
    db.commit()

    return ok({
        "success_count": success,
        "updated_count": updated,
        "skipped_count": skipped,
        "duplicates_in_batch": duplicates_in_batch,
    })


@router.post("/list")
async def list_idioms(req: IdiomListRequest, db: Session = Depends(get_db)):
    """题目列表（关键词 / 启用状态筛选 + 分页）。"""
    stmt = select(IdiomQuestion)
    count_stmt = select(func.count()).select_from(IdiomQuestion)

    conditions = []
    if req.keyword:
        like = f"%{req.keyword}%"
        conditions.append(or_(IdiomQuestion.prompt.like(like), IdiomQuestion.answer.like(like)))
    if req.enabled is not None:
        conditions.append(IdiomQuestion.enabled.is_(req.enabled))
    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(IdiomQuestion.id.desc()).offset((req.page - 1) * req.size).limit(req.size)
    ).all()

    return ok({
        "list": [_to_dict(q) for q in rows],
        "total": total,
        "page": req.page,
        "size": req.size,
    })


@router.post("/update")
async def update_idiom(
    req: IdiomUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """编辑单条题目。"""
    q = db.get(IdiomQuestion, req.question_id)
    if not q:
        raise _not_found("题目不存在")

    if req.prompt is not None:
        q.prompt = req.prompt.strip()
    if req.answer is not None:
        q.answer = req.answer.strip()
    if req.distractors is not None:
        q.distractors = json.dumps(req.distractors, ensure_ascii=False) if req.distractors else None
    if req.difficulty is not None:
        q.difficulty = req.difficulty
    if req.enabled is not None:
        q.enabled = req.enabled

    Repo(db).add_admin_log(
        admin_id=admin.id,
        action="idiom_update",
        target_type="idiom_question",
        target_id=q.id,
        detail=f"更新成语题目 {q.prompt}",
    )
    db.commit()

    return ok({"question": _to_dict(q)})


@router.post("/delete")
async def delete_idiom(
    req: IdiomDeleteRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除单条题目。"""
    q = db.get(IdiomQuestion, req.question_id)
    if not q:
        raise _not_found("题目不存在")

    prompt = q.prompt
    db.delete(q)
    Repo(db).add_admin_log(
        admin_id=admin.id,
        action="idiom_delete",
        target_type="idiom_question",
        target_id=req.question_id,
        detail=f"删除成语题目 {prompt}",
    )
    db.commit()

    return ok({"deleted_id": req.question_id})


@router.post("/batch-delete")
async def batch_delete_idioms(
    req: IdiomBatchDeleteRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量删除题目。"""
    rows = db.scalars(
        select(IdiomQuestion).where(IdiomQuestion.id.in_(req.question_ids))
    ).all()
    deleted = len(rows)
    for q in rows:
        db.delete(q)

    Repo(db).add_admin_log(
        admin_id=admin.id,
        action="idiom_batch_delete",
        target_type="idiom_question",
        detail=f"批量删除成语题目 {deleted} 条：{req.question_ids}",
    )
    db.commit()

    return ok({"deleted_count": deleted})