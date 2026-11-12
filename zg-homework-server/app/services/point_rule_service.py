"""积分规则服务（PRD 10.3、5.8.3）。

- 所有积分发放统一读 `point_rules`，修改后立即生效
- 规则 `enabled=false` 不发放
- 规则服务缓存 60 秒，admin update 时失效（PRD 10.3）
"""

import json
import threading
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.models.entities import PointRule

# 缓存有效期（秒），PRD 10.3
CACHE_TTL = 60


@dataclass(frozen=True)
class Rule:
    """规则快照。frozen 保证缓存对象不可被调用方意外修改。"""

    rule_key: str
    rule_name: str
    points: int
    daily_limit: int | None
    extra_config: dict | None
    enabled: bool

    @classmethod
    def from_model(cls, m: PointRule) -> "Rule":
        extra = None
        if m.extra_config:
            try:
                extra = json.loads(m.extra_config)
            except (ValueError, TypeError):
                # 历史脏数据不应导致整个规则表不可用
                extra = None
        return cls(
            rule_key=m.rule_key,
            rule_name=m.rule_name,
            points=m.points,
            daily_limit=m.daily_limit,
            extra_config=extra,
            enabled=bool(m.enabled),
        )


class RuleService:
    """带 TTL 缓存的规则读取服务。

    线程安全：进程内单例，配锁防止并发下重复回源。
    缓存按 rule_key 分项存储，便于 admin 改单条规则时精确失效。
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Rule]] = {}
        self._lock = threading.Lock()

    def get(self, db: Session, rule_key: str, use_cache: bool = True) -> Rule | None:
        """取单条规则。未命中缓存则查库。"""
        if use_cache:
            with self._lock:
                hit = self._cache.get(rule_key)
                if hit and (time.monotonic() - hit[0]) < CACHE_TTL:
                    return hit[1]

        model = Repo(db).get_rule_by_key(rule_key)
        if model is None:
            return None

        rule = Rule.from_model(model)
        with self._lock:
            self._cache[rule_key] = (time.monotonic(), rule)
        return rule

    def invalidate(self, rule_key: str | None = None) -> None:
        """失效缓存。传 rule_key 只失效该条；不传则全清。

        admin 修改规则后调用，保证「修改后新发放立即按新值执行」（PRD 5.8.3）。
        """
        with self._lock:
            if rule_key is None:
                self._cache.clear()
            else:
                self._cache.pop(rule_key, None)

    def get_points(
        self,
        db: Session,
        rule_key: str,
        default: int = 0,
    ) -> int | None:
        """取规则积分值。

        返回 None 表示规则不存在或已禁用 —— 调用方应**跳过发放**（PRD 6）。
        """
        rule = self.get(db, rule_key)
        if rule is None or not rule.enabled:
            return None
        return rule.points

    def get_extra(self, db: Session, rule_key: str, key: str, default=None):
        """取扩展配置里的单项，如 single_article_limit。"""
        rule = self.get(db, rule_key)
        if rule is None or not rule.extra_config:
            return default
        return rule.extra_config.get(key, default)


# 进程内单例
rule_service = RuleService()