"""积分规则管理接口（PRD 5.8.3）。

- `rule_key` 不可改
- 修改立即生效（失效规则服务缓存），写 `admin_logs`
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.entities import PointRule, User
from app.utils.deps import require_admin
from app.utils.response import CODE_BAD_REQUEST, CODE_NOT_FOUND, ok
from app.services.point_rule_service import rule_service

router = APIRouter(
    prefix="/admin/rules",
    tags=["积分规则"],
    dependencies=[Depends(require_admin)],
)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


# ---------------- 出入参 ----------------


class RuleUpdateRequest(BaseModel):
    """单条规则更新。`rule_key` 只用于定位，不可修改。

    除 rule_key 外均为可选：未传的字段保持不变（部分更新）。
    """

    rule_key: str
    points: int | None = Field(None, ge=0, le=10000)
    daily_limit: int | None = Field(None, ge=0)
    extra_config: str | None = None  # JSON 字符串
    enabled: bool | None = None

    @field_validator("extra_config")
    @classmethod
    def check_json(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        try:
            json.loads(v)
        except ValueError as exc:
            raise ValueError(f"extra_config 必须是合法 JSON：{exc}") from exc
        return v


class RuleBatchItem(BaseModel):
    rule_key: str
    points: int | None = Field(None, ge=0, le=10000)
    daily_limit: int | None = Field(None, ge=0)
    extra_config: str | None = None
    enabled: bool | None = None

    @field_validator("extra_config")
    @classmethod
    def check_json(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        try:
            json.loads(v)
        except ValueError as exc:
            raise ValueError(f"extra_config 必须是合法 JSON：{exc}") from exc
        return v


class RuleBatchUpdateRequest(BaseModel):
    rules: list[RuleBatchItem] = Field(..., min_length=1, max_length=50)


class RuleDetailRequest(BaseModel):
    rule_key: str


# ---------------- 工具 ----------------


def _rule_to_dict(r: PointRule) -> dict:
    return {
        "id": r.id,
        "rule_key": r.rule_key,
        "rule_name": r.rule_name,
        "points": r.points,
        "daily_limit": r.daily_limit,
        "extra_config": r.extra_config,
        "enabled": bool(r.enabled),
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _apply(rule: PointRule, req) -> None:
    """按请求更新规则字段；None 表示不修改。"""
    if req.points is not None:
        rule.points = req.points
    if req.daily_limit is not None:
        rule.daily_limit = req.daily_limit
    if req.extra_config is not None:
        rule.extra_config = req.extra_config
    if req.enabled is not None:
        rule.enabled = req.enabled


# ---------------- 接口 ----------------


@router.post("/list")
async def rules_list(db: Session = Depends(get_db)):
    """查看全部规则（PRD 5.8.3）。无入参，不要求 Body。"""
    rules = Repo(db).list_point_rules()
    return ok({"list": [_rule_to_dict(r) for r in rules], "total": len(rules)})


@router.post("/detail")
async def rules_detail(req: RuleDetailRequest, db: Session = Depends(get_db)):
    """规则详情。"""
    rule = Repo(db).get_rule_by_key(req.rule_key)
    if not rule:
        raise _not_found(f"规则 {req.rule_key} 不存在")
    return ok({"rule": _rule_to_dict(rule)})


@router.post("/update")
async def rules_update(
    req: RuleUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """更新单条规则。修改后缓存立即失效，新发放按新值执行。"""
    repo = Repo(db)
    rule = repo.get_rule_by_key(req.rule_key)
    if not rule:
        raise _not_found(f"规则 {req.rule_key} 不存在")

    before = _rule_to_dict(rule)
    _apply(rule, req)
    rule.updated_by = admin.id

    repo.add_admin_log(
        admin_id=admin.id,
        action="rule_update",
        target_type="point_rule",
        target_id=rule.id,
        detail=json.dumps(
            {"rule_key": req.rule_key, "before": before, "after": _rule_to_dict(rule)},
            ensure_ascii=False,
        ),
    )
    db.commit()

    # 缓存失效 —— 保证「修改后立即生效」（PRD 5.8.3）
    rule_service.invalidate(req.rule_key)

    return ok({"rule": _rule_to_dict(rule)})


@router.post("/batch-update")
async def rules_batch_update(
    req: RuleBatchUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批量更新规则。任一条目非法则整批拒绝（事务回滚）。"""
    repo = Repo(db)

    # 先校验全部，避免部分成功造成状态不一致
    seen: set[str] = set()
    updates: list[tuple[PointRule, RuleBatchItem]] = []
    for item in req.rules:
        if item.rule_key in seen:
            raise _bad_request(f"批量更新中 rule_key 重复：{item.rule_key}")
        seen.add(item.rule_key)

        rule = repo.get_rule_by_key(item.rule_key)
        if not rule:
            raise _not_found(f"规则 {item.rule_key} 不存在")
        updates.append((rule, item))

    details = []
    for rule, item in updates:
        before = _rule_to_dict(rule)
        _apply(rule, item)
        rule.updated_by = admin.id
        details.append({"rule_key": item.rule_key, "before": before, "after": _rule_to_dict(rule)})

    repo.add_admin_log(
        admin_id=admin.id,
        action="rule_batch_update",
        target_type="point_rule",
        detail=json.dumps(details, ensure_ascii=False),
    )
    db.commit()

    # 整批缓存失效
    rule_service.invalidate()

    return ok({
        "updated": [_rule_to_dict(r) for r, _ in updates],
        "count": len(updates),
    })