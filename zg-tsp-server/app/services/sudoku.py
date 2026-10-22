"""数独题目生成（PRD 5.6，决策 5：内置生成算法，不预置题库）。

算法：完整解生成（回溯 + 随机候选）→ 按难度挖空 → 校验唯一解。

难度定义（挖空比例）：
- easy   约 36 个空（保留 45 个提示数）
- medium 约 48 个空
- hard   约 54 个空
"""

import random
import threading
import time
from dataclasses import dataclass

# 难度 -> 目标空格数（9x9 = 81 格）
DIFFICULTY_HOLES = {
    "easy": 36,
    "medium": 48,
    "hard": 54,
}

BOARD_SIZE = 9
BOX_SIZE = 3
MAX_GENERATE_ATTEMPTS = 20


class SudokuError(Exception):
    """数独生成失败（极端情况下重试仍无解）。"""


def _empty_board() -> list[list[int]]:
    return [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def _can_place(board: list[list[int]], row: int, col: int, value: int) -> bool:
    """检查 value 放在 (row, col) 是否合法。"""
    # 同行
    for c in range(BOARD_SIZE):
        if c != col and board[row][c] == value:
            return False
    # 同列
    for r in range(BOARD_SIZE):
        if r != row and board[r][col] == value:
            return False
    # 同宫
    box_r = (row // BOX_SIZE) * BOX_SIZE
    box_c = (col // BOX_SIZE) * BOX_SIZE
    for r in range(box_r, box_r + BOX_SIZE):
        for c in range(box_c, box_c + BOX_SIZE):
            if (r, c) != (row, col) and board[r][c] == value:
                return False
    return True


def _solve(board: list[list[int]], limit: int = 2) -> int:
    """回溯求解，找到至多 limit 个解就停（用于唯一解校验）。返回解的个数。

    用 row = -1 表示「已填满」，而不是 (row, col) == (0, 0) ——
    后者在左上角为空时无法与「棋盘填满」区分。

    注意：递归返回时棋盘会被回溯清空，调用方若需保留解须自行拷贝。
    """
    row = col = -1
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] == 0:
                row, col = r, c
                break
        if row != -1:
            break

    if row == -1:
        return 1  # 已填满，找到一个解

    found = 0
    for v in range(1, BOARD_SIZE + 1):
        if _can_place(board, row, col, v):
            board[row][col] = v
            found += _solve(board, limit)
            board[row][col] = 0
            if found >= limit:
                return found
    return found


def _generate_complete_board(rng: random.Random) -> list[list[int]]:
    """生成一个完整合法解。"""
    board = _empty_board()

    def fill(idx: int) -> bool:
        if idx == BOARD_SIZE * BOARD_SIZE:
            return True
        row, col = divmod(idx, BOARD_SIZE)
        # 随机打乱候选顺序，避免每次生成同样的盘面
        nums = list(range(1, BOARD_SIZE + 1))
        rng.shuffle(nums)
        for v in nums:
            if _can_place(board, row, col, v):
                board[row][col] = v
                if fill(idx + 1):
                    return True
                board[row][col] = 0
        return False

    fill(0)
    return board


def count_solutions(board: list[list[int]]) -> int:
    """统计解的个数（最多数到 2，用于唯一性判断）。"""
    return _solve([row[:] for row in board], limit=2)


@dataclass(frozen=True)
class SudokuPuzzle:
    """数独题目。solution 仅服务端持有，不返回给前端。"""

    puzzle_id: str
    difficulty: str
    board: list[list[int]]  # 0 表示空格
    holes: int
    created_at: float


# 进程内题目缓存（puzzle_id -> 题目）
class PuzzleCache:
    """存放进行中的题目，TTL 30 分钟。服务端不持久化（PRD 4.1 无对应表）。"""

    def __init__(self) -> None:
        self._items: dict[str, SudokuPuzzle] = {}
        self._lock = threading.Lock()

    def put(self, puzzle: SudokuPuzzle) -> None:
        with self._lock:
            self._evict_expired()
            self._items[puzzle.puzzle_id] = puzzle

    def get(self, puzzle_id: str) -> SudokuPuzzle | None:
        with self._lock:
            self._evict_expired()
            return self._items.get(puzzle_id)

    def _evict_expired(self) -> None:
        ttl = 30 * 60
        now = time.time()
        expired = [k for k, v in self._items.items() if now - v.created_at > ttl]
        for k in expired:
            self._items.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


puzzle_cache = PuzzleCache()


def generate(difficulty: str = "easy", rng: random.Random | None = None) -> SudokuPuzzle:
    """生成一道数独题，保证**唯一解**。"""
    if difficulty not in DIFFICULTY_HOLES:
        raise SudokuError(f"难度必须是 {', '.join(DIFFICULTY_HOLES)} 之一")

    rng = rng or random.Random()
    target_holes = DIFFICULTY_HOLES[difficulty]

    for _ in range(MAX_GENERATE_ATTEMPTS):
        solution = _generate_complete_board(rng)
        board = [row[:] for row in solution]

        # 随机挖空
        cells = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)]
        rng.shuffle(cells)
        holes = 0
        for r, c in cells:
            if holes >= target_holes:
                break
            backup = board[r][c]
            board[r][c] = 0
            # 挖掉后必须仍是唯一解
            if count_solutions(board) == 1:
                holes += 1
            else:
                board[r][c] = backup  # 会产生多解，放回去

        import uuid

        puzzle = SudokuPuzzle(
            puzzle_id=uuid.uuid4().hex[:16],
            difficulty=difficulty,
            board=board,
            holes=holes,
            created_at=time.time(),
        )
        puzzle_cache.put(puzzle)
        return puzzle

    raise SudokuError("题目生成失败，请重试")


def verify(puzzle: SudokuPuzzle, submission: list[list[int]]) -> bool:
    """校验学生提交的答案是否与标准解一致且合法。"""
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            v = submission[r][c]
            if not (1 <= v <= BOARD_SIZE):
                return False
            # 提示数必须保持不变
            if puzzle.board[r][c] != 0 and puzzle.board[r][c] != v:
                return False

    # 行/列/宫合法性
    for r in range(BOARD_SIZE):
        if len(set(submission[r])) != BOARD_SIZE:
            return False
    for c in range(BOARD_SIZE):
        if len({submission[r][c] for r in range(BOARD_SIZE)}) != BOARD_SIZE:
            return False
    for br in range(0, BOARD_SIZE, BOX_SIZE):
        for bc in range(0, BOARD_SIZE, BOX_SIZE):
            block = [submission[br + i][bc + j] for i in range(BOX_SIZE) for j in range(BOX_SIZE)]
            if len(set(block)) != BOARD_SIZE:
                return False

    return True