"""成语接龙题库服务（PRD 5.6，决策 4：题库由 admin 后台导入）。

- 抽题：随机取一道 enabled 的题目
- 干扰项：不足 2 个时从库中随机补齐（PRD 5.8.6）
- 会话：60 秒限时闯关，答对 +1/题（读 game_idiom 规则）
"""

import json
import random
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import IdiomQuestion

# 干扰项建议数量（PRD 5.8.6）
MIN_DISTRACTORS = 2

# 单次闯关时长（PRD 5.6）
GAME_DURATION_SECONDS = 60


@dataclass
class IdiomQuestionView:
    """返回给学生的题目：题干 + 4 个选项（含正确答案）。"""

    question_id: int
    prompt: str
    options: list[str]
    answer: str

    def public(self) -> dict:
        """对外不含 answer。"""
        return {
            "question_id": self.question_id,
            "prompt": self.prompt,
            "options": self.options,
        }


@dataclass
class IdiomSession:
    """一次闯关会话。服务端内存保存，不落库（PRD 4.1 无会话表）。"""

    session_id: str
    student_id: int
    started_at: float
    correct: int = 0
    wrong: int = 0
    used_ids: list[int] = field(default_factory=list)
    finished: bool = False
    # 当前待作答的题目：question 接口下发后保存，answer 时据此判定，
    # 避免每次 answer 都重新抽题导致判定对象与学生看到的题不一致
    current: IdiomQuestionView | None = None

    @property
    def elapsed_seconds(self) -> int:
        import time

        return int(time.time() - self.started_at)


def _parse_distractors(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def count_questions(db: Session, enabled_only: bool = True) -> int:
    stmt = select(func.count()).select_from(IdiomQuestion)
    if enabled_only:
        stmt = stmt.where(IdiomQuestion.enabled.is_(True))
    return db.scalar(stmt) or 0


def pick_question(
    db: Session,
    rng: random.Random | None = None,
    exclude_ids: list[int] | None = None,
) -> IdiomQuestionView | None:
    """随机抽一道题，并组装选项（含正确答案）。

    干扰项不足时从库中其他成语随机补齐（PRD 5.8.6）。
    """
    rng = rng or random.Random()

    stmt = select(IdiomQuestion).where(IdiomQuestion.enabled.is_(True))
    if exclude_ids:
        stmt = stmt.where(IdiomQuestion.id.notin_(exclude_ids))
    candidates = list(db.scalars(stmt))
    if not candidates:
        return None

    q = rng.choice(candidates)

    options = [q.answer]
    options.extend(_parse_distractors(q.distractors))

    # 干扰项补齐：去重后不足 MIN_DISTRACTORS+1 则从其他题目取答案补
    seen = {o for o in options}
    if len(options) < MIN_DISTRACTORS + 1:
        pool = db.scalars(
            select(IdiomQuestion).where(IdiomQuestion.id != q.id)
        ).all()
        rng.shuffle(pool)
        for other in pool:
            if other.answer and other.answer not in seen:
                options.append(other.answer)
                seen.add(other.answer)
            if len(options) >= MIN_DISTRACTORS + 1:
                break

    rng.shuffle(options)
    return IdiomQuestionView(
        question_id=q.id,
        prompt=q.prompt,
        options=options,
        answer=q.answer,
    )


def parse_items(payload: str) -> list[dict]:
    """解析导入的 JSON 文本。支持两种形态：

    1. 顶层数组：[{"prompt": "...", "answer": "..."}]
    2. {"items": [...]}
    """
    data = json.loads(payload)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("题库格式错误：应为数组或含 items 字段的对象")
    return data