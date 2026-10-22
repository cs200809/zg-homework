"""课后小游戏接口（PRD 5.6）。

**数独**：难度分级，计时，完成提交按难度给分（规则表）
**成语接龙**：60 秒限时闯关，答对 +1/题，题库由 admin 后台导入（决策 4）
**防沉迷**：每日游戏总积分上限 20（跨数独三档 + 成语接龙，PRD 第 6 节）
"""

import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repo import Repo
from app.db.session import get_db
from app.models.constants import POINT_TYPE_GAME, ROLE_STUDENT
from app.models.entities import GameRecord, User
from app.services import idiom, sudoku
from app.utils.deps import get_verified_user
from app.utils.response import CODE_BAD_REQUEST, CODE_FORBIDDEN, CODE_NOT_FOUND, ok

router = APIRouter(prefix="/games", tags=["游戏"])

# 数独难度 -> 积分规则（PRD 4.2）
SUDOKU_RULE_KEYS = {
    "easy": "game_sudoku_easy",
    "medium": "game_sudoku_medium",
    "hard": "game_sudoku_hard",
}


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": CODE_FORBIDDEN, "message": message})


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": CODE_NOT_FOUND, "message": message})


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": CODE_BAD_REQUEST, "message": message})


# ---------------- 会话缓存 ----------------


class SessionStore:
    """进行中的游戏会话（数独看 puzzle_cache，成语会话存在这里）。"""

    def __init__(self) -> None:
        self._items: dict[str, idiom.IdiomSession] = {}
        self._lock = threading.Lock()

    def put(self, s: idiom.IdiomSession) -> None:
        with self._lock:
            self._items[s.session_id] = s

    def get(self, session_id: str) -> idiom.IdiomSession | None:
        with self._lock:
            return self._items.get(session_id)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


sessions = SessionStore()


# ---------------- 出入参 ----------------


class SudokuStartRequest(BaseModel):
    difficulty: str = "easy"


class SudokuResultRequest(BaseModel):
    puzzle_id: str
    duration: int = Field(..., ge=0, le=36000)
    success: bool
    # 学生提交的 9x9 答案，用于服务端校验
    board: list[list[int]] | None = None


class IdiomQuestionRequest(BaseModel):
    session_id: str


class IdiomAnswerRequest(BaseModel):
    session_id: str
    answer: str = Field(..., min_length=1, max_length=50)


class IdiomResultRequest(BaseModel):
    session_id: str


class GameRecordsRequest(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


# ---------------- 数独 ----------------


@router.post("/sudoku/start")
async def sudoku_start(
    req: SudokuStartRequest,
    student: User = Depends(get_verified_user),
):
    """开始数独 —— 服务端按难度生成唯一解题目（决策 5）。无 DB 访问。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    difficulty = req.difficulty
    if difficulty not in SUDOKU_RULE_KEYS:
        raise _bad_request(f"难度必须是 {', '.join(SUDOKU_RULE_KEYS)} 之一")

    try:
        puzzle = sudoku.generate(difficulty)
    except sudoku.SudokuError as exc:
        raise _bad_request(str(exc)) from exc

    return ok({
        "puzzle_id": puzzle.puzzle_id,
        "difficulty": puzzle.difficulty,
        "board": puzzle.board,
        "holes": puzzle.holes,
    })


@router.post("/sudoku/result")
async def sudoku_result(
    req: SudokuResultRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """提交数独结果。成功按难度发分（PRD 5.6、4.2）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    puzzle = sudoku.puzzle_cache.get(req.puzzle_id)
    if not puzzle:
        raise _not_found("题目不存在或已过期，请重新开始")

    success = req.success
    if success and req.board is not None:
        # 学生提交了答案则服务端复核，防止伪造 success
        success = sudoku.verify(puzzle, req.board)

    points = 0
    if success:
        from app.services import point_service

        points = point_service.award_game(
            db,
            student.id,
            SUDOKU_RULE_KEYS[puzzle.difficulty],
            remark=f"数独-{puzzle.difficulty}",
            operator_id=student.id,
        )

    db.add(
        GameRecord(
            student_id=student.id,
            game_type="sudoku",
            difficulty=puzzle.difficulty,
            points=points,
            duration_seconds=req.duration,
        )
    )
    db.commit()

    return ok({
        "success": success,
        "points": points,
        "duration_seconds": req.duration,
    })


# ---------------- 成语接龙 ----------------


@router.post("/idiom/start")
async def idiom_start(
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """开始成语接龙 —— 60 秒限时闯关（PRD 5.6）。

    无入参接口：不声明 Body 依赖，客户端传空 Body 或完全不传均可。
    """
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    total = idiom.count_questions(db, enabled_only=True)
    if total == 0:
        raise _not_found("题库为空，请联系管理员导入题目")

    s = idiom.IdiomSession(
        session_id=secrets.token_hex(8),
        student_id=student.id,
        started_at=time.time(),
    )
    sessions.put(s)

    return ok({
        "session_id": s.session_id,
        "duration_seconds": idiom.GAME_DURATION_SECONDS,
        "total_questions": total,
    })


@router.post("/idiom/question")
async def idiom_question(
    req: IdiomQuestionRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """取下一题（PRD 5.6）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    s = sessions.get(req.session_id)
    if not s or s.student_id != student.id:
        raise _not_found("会话不存在或已过期，请重新开始")

    if s.elapsed_seconds >= idiom.GAME_DURATION_SECONDS:
        s.finished = True
        raise _bad_request("时间已到，请提交结果")

    q = idiom.pick_question(db, exclude_ids=s.used_ids)
    if q is None:
        q = idiom.pick_question(db)  # 题都出过了，允许重复

    # 记录当前题，answer 接口据此判定
    s.current = q

    return ok({
        "session_id": s.session_id,
        "question": q.public(),
        "elapsed_seconds": s.elapsed_seconds,
        "remaining_seconds": max(0, idiom.GAME_DURATION_SECONDS - s.elapsed_seconds),
    })


@router.post("/idiom/answer")
async def idiom_answer(
    req: IdiomAnswerRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """提交答案 —— 答对 +1/题（读 game_idiom 规则，PRD 4.2）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    s = sessions.get(req.session_id)
    if not s or s.student_id != student.id:
        raise _not_found("会话不存在或已过期，请重新开始")

    if s.finished or s.elapsed_seconds >= idiom.GAME_DURATION_SECONDS:
        s.finished = True
        raise _bad_request("时间已到，请提交结果")

    q = s.current
    if q is None:
        raise _bad_request("请先获取题目")

    correct = req.answer.strip() == q.answer
    if correct:
        s.correct += 1
        if q.question_id not in s.used_ids:
            s.used_ids.append(q.question_id)
    else:
        s.wrong += 1

    # 一题一答，用完即清空，防止重复提交同一题刷分
    s.current = None

    db.commit()
    return ok({
        "correct": correct,
        "right_answer": q.answer,
        "correct_count": s.correct,
        "wrong_count": s.wrong,
        "remaining_seconds": max(0, idiom.GAME_DURATION_SECONDS - s.elapsed_seconds),
    })


@router.post("/idiom/result")
async def idiom_result(
    req: IdiomResultRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """提交闯关结果，按答对题数发分（PRD 5.6）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可玩游戏")

    s = sessions.get(req.session_id)
    if not s or s.student_id != student.id:
        raise _not_found("会话不存在或已过期")

    from app.services import point_service

    # 答对每题 +1 分（读 game_idiom），逐题发放以正确反映题数，
    # 每日合计 20 分上限由 award_game 内部处理（超出部分自动截断）
    points = 0
    for i in range(s.correct):
        gained = point_service.award_game(
            db,
            student.id,
            "game_idiom",
            remark=f"成语接龙 答对第 {i + 1} 题",
            operator_id=student.id,
        )
        if gained == 0:
            break  # 已达当日游戏上限
        points += gained

    db.add(
        GameRecord(
            student_id=student.id,
            game_type="idiom",
            points=points,
            duration_seconds=s.elapsed_seconds,
        )
    )
    s.finished = True
    db.commit()

    return ok({
        "correct_count": s.correct,
        "wrong_count": s.wrong,
        "duration_seconds": s.elapsed_seconds,
        "points": points,
    })


# ---------------- 游戏记录 ----------------


@router.post("/records")
async def game_records(
    req: GameRecordsRequest,
    student: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """我的游戏记录（分页）。"""
    if student.role != ROLE_STUDENT:
        raise _forbidden("仅学生可查看游戏记录")

    from sqlalchemy import func, select

    stmt = select(GameRecord).where(GameRecord.student_id == student.id)
    count_stmt = select(func.count()).select_from(GameRecord).where(
        GameRecord.student_id == student.id
    )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(GameRecord.id.desc())
        .offset((req.page - 1) * req.size)
        .limit(req.size)
    ).all()

    return ok({
        "list": [
            {
                "id": r.id,
                "game_type": r.game_type,
                "difficulty": r.difficulty,
                "points": r.points,
                "duration_seconds": r.duration_seconds,
                "play_date": r.play_date.isoformat() if r.play_date else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": req.page,
        "size": req.size,
    })