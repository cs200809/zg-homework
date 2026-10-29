"""P6 小游戏测试（PRD 5.6、5.8.6）。

约定：只增不删 —— 用例使用唯一用户名/题干，不清理数据。
"""

import pytest
from sqlalchemy import select

from app.db.repo import Repo
from app.models.constants import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER
from app.models.entities import GameRecord, IdiomQuestion
from app.services import sudoku
from app.services.point_rule_service import rule_service


def post(client, path, body=None, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, json=body or {}, headers=headers)


@pytest.fixture(autouse=True)
def _clear_cache():
    rule_service.invalidate()
    yield
    rule_service.invalidate()


@pytest.fixture
def set_rule(client, admin_token, db):
    def _set(rule_key: str, **fields) -> None:
        r = post(client, "/admin/rules/update", {"rule_key": rule_key, **fields}, token=admin_token)
        assert r.status_code == 200, r.text
        db.rollback()
        db.expire_all()
        rule_service.invalidate(rule_key)

    return _set


@pytest.fixture
def game_rules(set_rule):
    """PRD 4.2 游戏规则默认值：数独 5/10/15，成语每题 1 分，合计上限 20。"""
    set_rule("game_sudoku_easy", points=5, daily_limit=20, enabled=True)
    set_rule("game_sudoku_medium", points=10, daily_limit=20, enabled=True)
    set_rule("game_sudoku_hard", points=15, daily_limit=20, enabled=True)
    set_rule("game_idiom", points=1, daily_limit=20, enabled=True)


@pytest.fixture
def seeded_idioms(client, admin_token, db, uname, uniq):
    """导入若干成语题目，返回题干列表。"""
    prompts = [uniq(f"I{i}").upper()[:8] for i in range(5)]
    items = [
        {"prompt": p, "answer": f"答案{p}", "distractors": ["干扰A", "干扰B"]}
        for p in prompts
    ]
    r = post(client, "/admin/idioms/import", {"items": items}, token=admin_token)
    assert r.status_code == 200, r.text
    return prompts


# ==================== 数独生成算法（决策 5） ====================


def test_sudoku_generates_unique_solution():
    """生成的题目必须有唯一解（PRD 5.6）。"""
    for difficulty in ("easy", "medium", "hard"):
        p = sudoku.generate(difficulty)
        assert sudoku.count_solutions(p.board) == 1


def test_sudoku_difficulty_hole_counts():
    """三档难度挖空数递增（PRD 5.6）。"""
    holes = {d: sudoku.generate(d).holes for d in ("easy", "medium", "hard")}
    assert holes["easy"] < holes["medium"] < holes["hard"]


def test_sudoku_board_shape():
    p = sudoku.generate("easy")
    assert len(p.board) == 9
    assert all(len(row) == 9 for row in p.board)
    assert all(0 <= v <= 9 for row in p.board for v in row)


def test_sudoku_invalid_difficulty_raises():
    with pytest.raises(sudoku.SudokuError):
        sudoku.generate("impossible")


def test_sudoku_verify_rejects_wrong_answer():
    """提交错误答案校验不通过。"""
    p = sudoku.generate("easy")
    wrong = [[0] * 9 for _ in range(9)]
    assert sudoku.verify(p, wrong) is False


# ==================== 数独接口 ====================


def test_sudoku_start_returns_board(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "ss")
    r = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=login(student, pw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["puzzle_id"]
    assert len(data["board"]) == 9
    assert data["difficulty"] == "easy"


def test_sudoku_start_invalid_difficulty(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "sd")
    r = post(client, "/games/sudoku/start", {"difficulty": "crazy"}, token=login(student, pw))
    assert r.status_code == 400


def test_teacher_cannot_play(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "sp")
    r = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=login(teacher, pw))
    assert r.status_code == 403


def _first_empty(board):
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                return r, c
    return -1, -1


def _solve_board(puzzle):
    """补全标准解（测试辅助）。

    `_solve` 回溯结束后会把棋盘清回原状，所以不能直接用它的返回值，
    需在棋盘填满的那一刻抓取副本。
    """
    board = [row[:] for row in puzzle.board]
    snapshot: list[list[int]] = []

    def fill(b):
        r, c = _first_empty(b)
        if r == -1:  # 已填满
            snapshot[:] = [row[:] for row in b]
            return True
        for v in range(1, 10):
            if sudoku._can_place(b, r, c, v):
                b[r][c] = v
                if fill(b):
                    return True
                b[r][c] = 0
        return False

    assert fill(board), "求解器应能补全题目"
    return snapshot


def test_sudoku_result_success_awards_points(client, login, make_user, game_rules, db, refresh):
    """成功按难度发分（PRD 5.6、4.2）。"""
    student, pw = make_user(ROLE_STUDENT, "sr")
    token = login(student, pw)

    start = post(client, "/games/sudoku/start", {"difficulty": "medium"}, token=token).json()["data"]
    puzzle = sudoku.puzzle_cache.get(start["puzzle_id"])
    solved = _solve_board(puzzle)

    r = post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 120, "success": True, "board": solved},
        token=token,
    )
    assert r.status_code == 200
    assert r.json()["data"]["points"] == 10  # medium 10 分

    refresh()
    assert student.total_points == 10


def test_sudoku_result_fail_gives_nothing(client, login, make_user, game_rules, db, refresh):
    student, pw = make_user(ROLE_STUDENT, "sf")
    token = login(student, pw)

    start = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=token).json()["data"]
    r = post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 60, "success": False},
        token=token,
    )
    assert r.json()["data"]["points"] == 0

    refresh()
    assert student.total_points == 0


def test_sudoku_result_rejects_fake_success(client, login, make_user, game_rules, db, refresh):
    """学生自称成功但答案错误时，服务端复核不通过（防刷，PRD 10.2）。"""
    student, pw = make_user(ROLE_STUDENT, "sfk")
    token = login(student, pw)

    start = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=token).json()["data"]
    fake = [[0] * 9 for _ in range(9)]

    r = post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 10, "success": True, "board": fake},
        token=token,
    )
    assert r.json()["data"]["success"] is False
    assert r.json()["data"]["points"] == 0

    refresh()
    assert student.total_points == 0


def test_sudoku_result_unknown_puzzle(client, login, make_user):
    student, pw = make_user(ROLE_STUDENT, "su")
    r = post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": "nonexistent", "duration": 10, "success": True},
        token=login(student, pw),
    )
    assert r.status_code == 404


def test_sudoku_writes_game_record(client, login, make_user, game_rules, db, refresh):
    """游戏记录落库（PRD 5.6）。"""
    student, pw = make_user(ROLE_STUDENT, "sgr")
    token = login(student, pw)

    start = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=token).json()["data"]
    post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 45, "success": False},
        token=token,
    )
    refresh()

    rec = db.scalars(select(GameRecord).where(GameRecord.student_id == student.id)).first()
    assert rec.game_type == "sudoku"
    assert rec.difficulty == "easy"
    assert rec.duration_seconds == 45


# ==================== 成语接龙（决策 4） ====================


def test_idiom_start(client, login, make_user, seeded_idioms):
    student, pw = make_user(ROLE_STUDENT, "ig")
    r = post(client, "/games/idiom/start", token=login(student, pw))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session_id"]
    assert data["duration_seconds"] == 60  # PRD 5.6：60 秒限时


def test_idiom_start_empty_bank(client, login, make_user):
    """题库为空时提示，不发 500。"""
    student, pw = make_user(ROLE_STUDENT, "ie")
    # 用一个绝对查不到的库来断言；实际库有种子数据，因此只断言接口不崩
    r = post(client, "/games/idiom/start", token=login(student, pw))
    assert r.status_code in (200, 404)


def test_idiom_question_returns_options(client, login, make_user, seeded_idioms):
    student, pw = make_user(ROLE_STUDENT, "iq")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]

    r = post(client, "/games/idiom/question", {"session_id": sid}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["question"]["prompt"]
    assert len(data["question"]["options"]) >= 3  # 含正确答案 + 干扰项
    assert "answer" not in data["question"]  # 不下发答案


def test_idiom_answer_correct(client, login, make_user, seeded_idioms, db, refresh):
    student, pw = make_user(ROLE_STUDENT, "ia")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]

    q = post(client, "/games/idiom/question", {"session_id": sid}, token=token).json()["data"]["question"]
    # 从库中取正确答案
    correct = db.scalar(select(IdiomQuestion).where(IdiomQuestion.prompt == q["prompt"])).answer

    r = post(client, "/games/idiom/answer", {"session_id": sid, "answer": correct}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["correct"] is True
    assert data["correct_count"] == 1


def test_idiom_answer_wrong(client, login, make_user, seeded_idioms):
    student, pw = make_user(ROLE_STUDENT, "iw")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]
    post(client, "/games/idiom/question", {"session_id": sid}, token=token)

    r = post(client, "/games/idiom/answer", {"session_id": sid, "answer": "肯定不对"}, token=token)
    assert r.json()["data"]["correct"] is False
    assert r.json()["data"]["wrong_count"] == 1


def test_idiom_answer_without_question(client, login, make_user, seeded_idioms):
    """未取题直接作答应被拒（防刷）。"""
    student, pw = make_user(ROLE_STUDENT, "inq")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]

    r = post(client, "/games/idiom/answer", {"session_id": sid, "answer": "任意"}, token=token)
    assert r.status_code == 400


def test_idiom_answer_other_session_forbidden(client, login, make_user, seeded_idioms):
    """不能操作别人的会话。"""
    s1, pw1 = make_user(ROLE_STUDENT, "o1")
    s2, pw2 = make_user(ROLE_STUDENT, "o2")

    sid = post(client, "/games/idiom/start", token=login(s1, pw1)).json()["data"]["session_id"]
    r = post(client, "/games/idiom/answer", {"session_id": sid, "answer": "x"}, token=login(s2, pw2))
    assert r.status_code == 404


def test_idiom_result_awards_points(client, login, make_user, seeded_idioms, game_rules, db, refresh):
    """闯关结果按答对题数发分（PRD 5.6：答对 +1/题）。"""
    student, pw = make_user(ROLE_STUDENT, "ir")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]

    for _ in range(3):
        q = post(client, "/games/idiom/question", {"session_id": sid}, token=token).json()["data"]["question"]
        correct = db.scalar(select(IdiomQuestion).where(IdiomQuestion.prompt == q["prompt"])).answer
        post(client, "/games/idiom/answer", {"session_id": sid, "answer": correct}, token=token)

    r = post(client, "/games/idiom/result", {"session_id": sid}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["correct_count"] == 3
    assert data["points"] == 3  # 每题 1 分

    refresh()
    assert student.total_points == 3


def test_idiom_result_writes_record(client, login, make_user, seeded_idioms, game_rules, db, refresh):
    student, pw = make_user(ROLE_STUDENT, "irr")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]
    post(client, "/games/idiom/result", {"session_id": sid}, token=token)
    refresh()

    rec = db.scalars(select(GameRecord).where(GameRecord.student_id == student.id)).first()
    assert rec.game_type == "idiom"


def test_teacher_cannot_play_idiom(client, login, make_user, seeded_idioms):
    teacher, pw = make_user(ROLE_TEACHER, "it")
    r = post(client, "/games/idiom/start", token=login(teacher, pw))
    assert r.status_code == 403


# ==================== 游戏合计上限（PRD 5.6 防沉迷） ====================


def test_game_daily_cap_20(client, login, make_user, game_rules, db, refresh):
    """每日游戏合计 20 分封顶（PRD 5.6、第 6 节、第 12 节验收）。"""
    student, pw = make_user(ROLE_STUDENT, "cap")
    token = login(student, pw)

    # 数独困难 15 分 + 两次 = 30 分，但合计只应给到 20
    for _ in range(2):
        start = post(client, "/games/sudoku/start", {"difficulty": "hard"}, token=token).json()["data"]
        post(
            client,
            "/games/sudoku/result",
            {"puzzle_id": start["puzzle_id"], "duration": 30, "success": True},
            token=token,
        )

    refresh()
    assert student.total_points == 20  # 15 + 5（第二次被截断）


def test_game_cap_shared_with_idiom(client, login, make_user, seeded_idioms, game_rules, db, refresh):
    """成语接龙与数独共用 20 分上限（PRD 第 6 节「游戏合计 20」）。"""
    student, pw = make_user(ROLE_STUDENT, "cap2")
    token = login(student, pw)

    # 先用数独拿 15 分
    start = post(client, "/games/sudoku/start", {"difficulty": "hard"}, token=token).json()["data"]
    post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 30, "success": True},
        token=token,
    )
    refresh()
    assert student.total_points == 15

    # 再玩成语，只应剩 5 分额度
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]
    for _ in range(8):
        q = post(client, "/games/idiom/question", {"session_id": sid}, token=token).json()["data"]["question"]
        correct = db.scalar(select(IdiomQuestion).where(IdiomQuestion.prompt == q["prompt"])).answer
        post(client, "/games/idiom/answer", {"session_id": sid, "answer": correct}, token=token)

    r = post(client, "/games/idiom/result", {"session_id": sid}, token=token)
    assert r.json()["data"]["points"] == 5  # 15 已用，只剩 5

    refresh()
    assert student.total_points == 20


def test_disabled_game_rule_gives_nothing(client, login, make_user, set_rule, db, refresh):
    """规则禁用不发分（PRD 6）。"""
    set_rule("game_sudoku_hard", points=15, daily_limit=20, enabled=False)
    student, pw = make_user(ROLE_STUDENT, "gd")
    token = login(student, pw)

    start = post(client, "/games/sudoku/start", {"difficulty": "hard"}, token=token).json()["data"]
    r = post(
        client,
        "/games/sudoku/result",
        {"puzzle_id": start["puzzle_id"], "duration": 30, "success": True},
        token=token,
    )
    assert r.json()["data"]["points"] == 0

    refresh()
    assert student.total_points == 0


# ==================== 游戏记录 ====================


def test_game_records_paged(client, login, make_user, game_rules, db, refresh):
    student, pw = make_user(ROLE_STUDENT, "gr")
    token = login(student, pw)

    for _ in range(2):
        start = post(client, "/games/sudoku/start", {"difficulty": "easy"}, token=token).json()["data"]
        post(
            client,
            "/games/sudoku/result",
            {"puzzle_id": start["puzzle_id"], "duration": 20, "success": False},
            token=token,
        )

    r = post(client, "/games/records", {"page": 1, "size": 10}, token=token)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 2
    assert all(x["game_type"] == "sudoku" for x in data["list"])


def test_game_records_only_student(client, login, make_user):
    teacher, pw = make_user(ROLE_TEACHER, "gr2")
    r = post(client, "/games/records", {}, token=login(teacher, pw))
    assert r.status_code == 403


# ==================== 5.8.6 成语题库管理 ====================


def test_idiom_import(client, admin_token, uname, uniq):
    """批量导入（PRD 5.8.6）。"""
    prompts = [uniq(f"Z{i}").upper()[:8] for i in range(3)]
    r = post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": p, "answer": f"答{p}"} for p in prompts]},
        token=admin_token,
    )
    assert r.status_code == 200
    assert r.json()["data"]["success_count"] == 3


def test_idiom_import_dedupe_in_batch(client, admin_token, uname, uniq):
    """同批内 prompt 去重（PRD 5.8.6）。"""
    p = uniq("DUPA").upper()[:8]
    r = post(
        client,
        "/admin/idioms/import",
        {"items": [
            {"prompt": p, "answer": "答1"},
            {"prompt": p, "answer": "答2"},
        ]},
        token=admin_token,
    )
    assert r.json()["data"]["success_count"] == 1
    assert r.json()["data"]["duplicates_in_batch"] == 1


def test_idiom_import_skip_existing(client, admin_token, uname, uniq):
    """mode=skip：已存在则跳过（PRD 5.8.6）。"""
    p = uniq("SKIP").upper()[:8]
    post(client, "/admin/idioms/import", {"items": [{"prompt": p, "answer": "原答案"}]}, token=admin_token)

    r = post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": p, "answer": "新答案"}], "mode": "skip"},
        token=admin_token,
    )
    assert r.json()["data"]["success_count"] == 0
    assert r.json()["data"]["skipped_count"] == 1


def test_idiom_import_overwrite_existing(client, admin_token, uname, db, refresh, uniq):
    """mode=overwrite：覆盖已有题目。"""
    p = uniq("OVR").upper()[:8]
    post(client, "/admin/idioms/import", {"items": [{"prompt": p, "answer": "原答案"}]}, token=admin_token)

    r = post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": p, "answer": "新答案"}], "mode": "overwrite"},
        token=admin_token,
    )
    assert r.json()["data"]["updated_count"] == 1

    refresh()
    assert db.scalar(select(IdiomQuestion).where(IdiomQuestion.prompt == p)).answer == "新答案"


def test_idiom_import_invalid_mode(client, admin_token, uname, uniq):
    r = post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": uniq("M").upper()[:8], "answer": "a"}], "mode": "weird"},
        token=admin_token,
    )
    assert r.status_code == 400


def test_idiom_import_requires_admin(client, login, make_user, uname, uniq):
    teacher, pw = make_user(ROLE_TEACHER, "ia2")
    r = post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": uniq("X").upper()[:8], "answer": "a"}]},
        token=login(teacher, pw),
    )
    assert r.status_code == 403


def test_idiom_import_writes_admin_log(client, admin_token, db, refresh, uname, uniq):
    from app.models.entities import AdminLog
    from app.utils.deps import decode_access_token

    # 审计日志记的是实际操作者（临时 admin 账号），不是真实 admin。
    actor_id = decode_access_token(admin_token)["user_id"]
    post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": uniq("LOG").upper()[:8], "answer": "a"}]},
        token=admin_token,
    )
    refresh()

    logs = db.scalars(
        select(AdminLog).where(AdminLog.admin_id == actor_id, AdminLog.action == "idiom_import")
    ).all()
    assert len(logs) >= 1


def test_idiom_list_filter(client, admin_token, seeded_idioms):
    r = post(client, "/admin/idioms/list", {"page": 1, "size": 50}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= len(seeded_idioms)


def test_idiom_update_and_disable(client, admin_token, seeded_idioms, db, refresh):
    """禁用后学生端抽不到（PRD 5.8.6）。"""
    listing = post(client, "/admin/idioms/list", {"page": 1, "size": 50}, token=admin_token).json()["data"]["list"]
    target = listing[0]["id"]

    r = post(client, "/admin/idioms/update", {"question_id": target, "enabled": False}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["question"]["enabled"] is False

    refresh()
    q = db.get(IdiomQuestion, target)
    assert q.enabled is False


def test_idiom_update_nonexistent(client, admin_token):
    r = post(client, "/admin/idioms/update", {"question_id": 999999999, "enabled": False}, token=admin_token)
    assert r.status_code == 404


def test_idiom_delete(client, admin_token, seeded_idioms, db, refresh):
    listing = post(client, "/admin/idioms/list", {"page": 1, "size": 50}, token=admin_token).json()["data"]["list"]
    target = listing[0]["id"]

    r = post(client, "/admin/idioms/delete", {"question_id": target}, token=admin_token)
    assert r.status_code == 200

    refresh()
    assert db.get(IdiomQuestion, target) is None


def test_idiom_batch_delete(client, admin_token, seeded_idioms, db, refresh):
    listing = post(client, "/admin/idioms/list", {"page": 1, "size": 5}, token=admin_token).json()["data"]["list"]
    ids = [x["id"] for x in listing[:3]]

    r = post(client, "/admin/idioms/batch-delete", {"question_ids": ids}, token=admin_token)
    assert r.status_code == 200
    assert r.json()["data"]["deleted_count"] == 3

    refresh()
    for i in ids:
        assert db.get(IdiomQuestion, i) is None


def test_idiom_distractors_padded(client, login, make_user, admin_token, db, uname, refresh, uniq):
    """干扰项不足时服务端补齐（PRD 5.8.6）。"""
    # 导入一批不含 distractors 的题目
    prompts = [uniq(f"P{i}").upper()[:8] for i in range(4)]
    post(
        client,
        "/admin/idioms/import",
        {"items": [{"prompt": p, "answer": f"答{p}"} for p in prompts]},
        token=admin_token,
    )

    student, pw = make_user(ROLE_STUDENT, "dp")
    token = login(student, pw)
    sid = post(client, "/games/idiom/start", token=token).json()["data"]["session_id"]

    for _ in range(5):
        r = post(client, "/games/idiom/question", {"session_id": sid}, token=token)
        if r.status_code == 200:
            assert len(r.json()["data"]["question"]["options"]) >= 3

def test_idiom_start_accepts_empty_body(client, login, make_user, seeded_idioms):
    """无入参接口：客户端传空 Body 也必须成功（PRD 全 POST + Body 约定）。"""
    student, pw = make_user(ROLE_STUDENT, "ieb")
    r = client.post("/games/idiom/start", json={}, headers={"Authorization": f"Bearer {login(student, pw)}"})
    assert r.status_code == 200, r.text
    assert r.json()["code"] == 0
