"""作业批改档位配置接口（admin）。

档位表 `homework_review_rules` 存「分数下限 → 积分」映射，admin 可改。
与 `point_rules` 的分工：point_rules 是单值规则（一次行为发多少分），
本表是档位区间映射（PRD 5.3 作业批改）。

修改立即生效（无缓存层 —— 匹配时直接查库）。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.entities import HomeworkReviewRule, User
from app.utils.deps import require_admin
from app.utils.response import CODE_BAD_REQUEST, CODE_NOT_FOUND, ok

router = APIRouter(
    prefix="/admin/homework-review-rules",
    tags=["作业批改档位"],
    dependencies=[Depends(require_admin)],
)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


# ---------------- 出入参 ----------------


class ReviewRuleCreateRequest(BaseModel):
    min_score: int = Field(..., ge=0, le=100)
    points: int = Field(..., ge=0, le=10000)


class ReviewRuleUpdateRequest(BaseModel):
    id: int
    points: int | None = Field(None, ge=0, le=10000)
    enabled: bool | None = None


# ---------------- 工具 ----------------


def _rule_to_dict(r: HomeworkReviewRule) -> dict:
    return {
        "id": r.id,
        "min_score": r.min_score,
        "points": r.points,
        "enabled": bool(r.enabled),
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ---------------- 接口 ----------------


@router.post("/list")
async def review_rules_list(db: Session = Depends(get_db)):
    """列出全部档位（按分数下限从高到低）。"""
    rules = Repo(db).list_review_rules()
    return ok({"list": [_rule_to_dict(r) for r in rules], "total": len(rules)})


@router.post("/create")
async def review_rule_create(
    req: ReviewRuleCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新增档位。`min_score` 唯一。"""
    repo = Repo(db)
    if repo.get_review_rule_by_min_score(req.min_score) is not None:
        raise _bad_request(f"该分数档位已存在：{req.min_score}")

    rule = repo.add_review_rule(
        HomeworkReviewRule(
            min_score=req.min_score,
            points=req.points,
            enabled=True,
            updated_by=admin.id,
        )
    )
    db.commit()
    db.refresh(rule)
    return ok({"rule": _rule_to_dict(rule)})


@router.post("/update")
async def review_rule_update(
    req: ReviewRuleUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新档位（积分值 / 启停）。未传的字段保持不变。"""
    repo = Repo(db)
    rule = repo.get_review_rule_by_id(req.id)
    if not rule:
        raise _not_found(f"档位 {req.id} 不存在")

    if req.points is not None:
        rule.points = req.points
    if req.enabled is not None:
        rule.enabled = req.enabled
    rule.updated_by = admin.id

    db.commit()
    db.refresh(rule)
    return ok({"rule": _rule_to_dict(rule)})
