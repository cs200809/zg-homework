"""端到端验收脚本。

对照 PRD 第 12 节验收标准，逐条调用真实接口验证。
用法：
    python zg-tsp-docs/scripts/acceptance_check.py
需要服务端运行在 127.0.0.1:8000。

设置 ACCEPTANCE_ADMIN_PASSWORD 为已有 admin 密码；本脚本会留下独立测试数据。
不会重置已有账号、删除数据或修改共享积分规则。
"""

import os
import secrets
import sys
import time
from datetime import datetime, timedelta

import httpx

BASE = "http://127.0.0.1:8000/homework_api"
SUFFIX = f"{secrets.randbelow(1000000):06d}"

results: list[tuple[bool, str, str]] = []
skipped: list[tuple[str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))


def skip(name: str, detail: str) -> None:
    skipped.append((name, detail))
    print(f"  跳过 {name} — {detail}")


def post(c: httpx.Client, path: str, body=None, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = c.post(f"{BASE}{path}", json=body or {}, headers=headers)
    try:
        return r.json()
    except Exception:
        return {"code": -1, "message": r.text[:120]}


def _phone(tag: int) -> str:
    """生成 11 位手机号（迭代 v2.1：注册用户名必须是手机号）。"""
    return f"138{SUFFIX}{tag:02d}"


def _make_pdf() -> bytes:
    """构造一份最小可读 PDF（用于验收「发布 PDF 文章」）。"""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 720, "Acceptance PDF")
    c.save()
    return buf.getvalue()


def _ensure_admin_login(c: httpx.Client) -> str | None:
    """使用显式提供的凭据登录，不修改已有账号。"""
    password = os.environ.get("ACCEPTANCE_ADMIN_PASSWORD")
    if not password:
        return None
    r = post(c, "/auth/login", {"username": "admin", "password": password})
    return r.get("data", {}).get("token") if r.get("code") == 0 else None


def main() -> int:
    c = httpx.Client(timeout=30)
    suffix = SUFFIX
    admin = _ensure_admin_login(c)
    if not admin:
        print("admin 登录失败；请提供有效的 ACCEPTANCE_ADMIN_PASSWORD，未修改账号。")
        return 2

    def login_created(role: str, response: dict) -> str:
        # 注册失败（包括手机号碰撞）时立即终止，不触碰既有账户。
        if response.get("code") != 0:
            raise RuntimeError(f"{role} 注册失败，停止验收: {response.get('message')}")
        login = post(c, "/auth/login", {"username": roles[role], "password": "test123456"})
        token = login.get("data", {}).get("token")
        if login.get("code") != 0 or not token:
            raise RuntimeError(f"{role} 登录失败，停止验收: {login.get('message')}")
        return token

    print("\n=== PRD 12 业务验收 ===")

    # 1. 四角色注册（迭代 v2.1：用户名必须是手机号；
    #    学生须带班级邀请码、家长须带学生绑定码）
    roles = {
        "teacher": _phone(1),
        "student": _phone(2),
        "parent": _phone(3),
    }

    # admin 建账号：老师需邀请码
    inv = post(c, "/admin/invite/create", {"count": 3, "expire_days": 7}, token=admin)
    codes = inv.get("data", {}).get("codes", [])

    if len(codes) < 3:
        print("生成测试邀请码失败，停止验收")
        return 2

    # 1a. 老师注册（一码一用）
    r = post(c, "/auth/register", {
        "username": roles["teacher"], "password": "test123456", "role": "teacher",
        "teacher_invite_code": codes[0],
    })
    check(r.get("code") == 0, "1. 老师可注册", f"code={r.get('code')} {r.get('message', '')}")

    check(True, "1b. admin 可登录")
    tokens = {"teacher": login_created("teacher", r)}

    # 老师建班 → 学生凭班级邀请码注册（自动入班）
    cls = post(c, "/classes/create", {"name": f"验收班{suffix}"}, token=tokens["teacher"])
    class_info = cls.get("data", {}).get("class")
    if not class_info:
        check(False, "1c. 老师建班", f"建班失败: {cls.get('message')}")
        return summary()
    cid = class_info["id"]
    class_invite = class_info["invite_code"]

    r = post(c, "/auth/register", {
        "username": roles["student"], "password": "test123456", "role": "student",
        "class_invite_code": class_invite,
    })
    check(r.get("code") == 0, "1c. 学生可注册（带班级邀请码）",
          f"code={r.get('code')} {r.get('message', '')}")
    tokens["student"] = login_created("student", r)

    # 家长凭学生绑定码注册（自动绑定）
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next((u for u in ul.get("data", {}).get("list", []) if u["username"] == roles["student"]), None)
    r = post(c, "/auth/register", {
        "username": roles["parent"], "password": "test123456", "role": "parent",
        "bind_code": (su or {}).get("bind_code"),
    })
    check(r.get("code") == 0, "1d. 家长可注册（带学生绑定码）",
          f"code={r.get('code')} {r.get('message', '')}")
    tokens["parent"] = login_created("parent", r)

    login_ok = all(tokens.values())
    login_detail = "teacher/student/parent" if login_ok else "有角色无法登录"
    check(login_ok, "1e. 四角色均可登录", login_detail)

    # 权限隔离：学生访问 admin 接口 403
    r = post(c, "/admin/stats/overview", token=tokens.get("student"))
    check(r.get("code") == 403, "1d. 权限隔离（学生访问 admin 接口 403）", f"code={r.get('code')}")

    # admin 不出现在排行榜
    r = post(c, "/points/rank", {"type": "total", "size": 50}, token=tokens.get("student"))
    admin_ids = [u for u in r.get("data", {}).get("list", []) if u["username"] == "admin"]
    check(not admin_ids, "1e. admin 不出现在排行榜")

    # 2. 老师邀请码一码一用
    r1 = post(c, "/auth/register", {
        "username": _phone(5), "password": "test123456",
        "role": "teacher", "teacher_invite_code": codes[1],
    })
    r2 = post(c, "/auth/register", {
        "username": _phone(6), "password": "test123456",
        "role": "teacher", "teacher_invite_code": codes[1],
    })
    check(r1.get("code") == 0 and r2.get("code") == 400
          and "邀请码不可用" in r2.get("message", ""),
          "2. 老师邀请码一码一用", f"首次={r1.get('code')} 二次={r2.get('code')}")

    r = post(c, "/auth/register", {
        "username": _phone(7), "password": "test123456",
        "role": "teacher", "teacher_invite_code": "INVALID1",
    })
    check(r.get("code") == 400 and "邀请码不存在" in r.get("message", ""), "2b. 无效邀请码被拒", f"{r.get('message')}")

    # 2c. 非手机号用户名被拒
    r = post(c, "/auth/register", {
        "username": "not_a_phone", "password": "test123456",
        "role": "teacher", "teacher_invite_code": codes[2],
    })
    check(r.get("code") == 400, "2c. 非手机号用户名被拒", f"code={r.get('code')}")

    # 3. admin 批量生成/撤销邀请码
    r = post(c, "/admin/invite/create", {"count": 5, "expire_days": 7}, token=admin)
    new_codes = r.get("data", {}).get("codes", [])
    lst = post(c, "/admin/invite/list", {"page": 1, "size": 50}, token=admin)
    target = next((i for i in lst.get("data", {}).get("list", []) if new_codes and i["code"] == new_codes[0]), None)
    rev = post(c, "/admin/invite/revoke", {"code_id": target["id"]}, token=admin) if target else {"code": -1}
    check(len(new_codes) == 5 and rev.get("code") == 0,
          "3. admin 批量生成/撤销邀请码", f"生成{len(new_codes)}个，撤销={rev.get('code')}")

    # 避免网络异常导致测试账号处于禁用状态。
    skip("4. 禁用立即生效", "避免禁用后异常无法恢复测试账号")
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next((u for u in ul.get("data", {}).get("list", []) if u["username"] == roles["student"]), None)

    # 18. 登录后可自助修改当前账户密码（PRD 5.1、迭代 v2.1 条目 11）
    #     入口：Web 右上角菜单 / 学生「我的」页；移动端四角色「我的」页
    #     本组会临时改动学生密码，末尾改回原值，避免在库里留下非预期密码的账号。
    old_pwd = "test123456"
    new_pwd = "test654321"

    # 18a. 原密码错误被拒
    r = post(c, "/auth/change-password",
             {"old_password": "wrong_password_xxx", "new_password": new_pwd},
             token=tokens["student"])
    check(r.get("code") == 400 and "原密码错误" in r.get("message", ""),
          "18a. 改密：原密码错误被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18b. 新密码短于 6 位被拒（服务端 Pydantic min_length=6，与两端前端一致）
    r = post(c, "/auth/change-password",
             {"old_password": old_pwd, "new_password": "12345"},
             token=tokens["student"])
    check(r.get("code") == 400 and "at least 6 characters" in r.get("message", ""),
          "18b. 改密：新密码短于 6 位被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18c. 新旧密码相同被拒
    r = post(c, "/auth/change-password",
             {"old_password": old_pwd, "new_password": old_pwd},
             token=tokens["student"])
    check(r.get("code") == 400 and "不能与原密码相同" in r.get("message", ""),
          "18c. 改密：新旧密码相同被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 不修改密码，避免网络中断后无法确认测试账号是否恢复。
    for name in ("18d. 改密成功", "18e. 新密码登录", "18f. 旧密码失效", "18g. 恢复原密码"):
        skip(name, "避免中断后测试账号密码无法恢复")

    skip("5. admin 无法禁用 admin", "避免对未知账号执行禁用")
    skip("6. 签到规则生效", "避免修改共享规则")
    skip("6b. 签到规则禁用", "避免修改共享规则")

    # 7. 文章管理权限
    art = post(c, "/articles/create", {"title": f"验收文章{suffix}", "content": "正文"}, token=admin)
    aid = art.get("data", {}).get("article", {}).get("id")
    if art.get("code") == 0 and aid is not None:
        teacher_list = post(c, "/articles/records", {"article_id": aid}, token=tokens["teacher"])
        check(teacher_list.get("code") == 403, "7. 老师仅能管自己的文章",
              f"老师查 admin 文章 code={teacher_list.get('code')}")
    else:
        skip("7. 文章权限", f"创建文章失败: {art.get('message')}")
    skip("7b. admin 删除文章", "禁止删除数据")

    # 8. 学生注册时已自动入班（迭代 v2.1）+ 老师布置作业
    my = post(c, "/classes/my", token=tokens["student"])
    joined = my.get("data", {}).get("classes", [])
    check(bool(joined) and joined[0].get("id") == cid,
          "8. 学生注册时自动加入班级",
          f"class_id={joined[0].get('id') if joined else None}")

    dl = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    hw = post(c, "/homework/create", {
        "class_id": cid, "title": f"验收作业{suffix}",
        "deadline": dl, "subject": "数学",
    }, token=tokens["teacher"])
    hid = hw.get("data", {}).get("homework", {}).get("id")
    check(hid is not None, "8b. 老师布置作业")

    # 9. 开始/提交 + 老师看到时间与用时
    post(c, "/homework/start", {"homework_id": hid}, token=tokens["student"])
    time.sleep(2)
    sub = c.post(f"{BASE}/homework/submit",
                  data={"homework_id": str(hid), "text_content": "答案"},
                  headers={"Authorization": f"Bearer {tokens['student']}"})
    sub = sub.json()
    recs = post(c, "/homework/records", {"homework_id": hid}, token=tokens["teacher"])
    row = recs.get("data", {}).get("records", [{}])[0]
    has_start = bool(row.get("start_time"))
    has_submit = bool(row.get("submit_time"))
    check(has_start and has_submit, "9. 老师能看到开始时间与提交时间",
          f"start={has_start} submit={has_submit}")

    skip("10. 固定作业积分", "不修改共享作业积分规则")

    # 只读取现有档位，按当前规则核验新建学生的首次批改与历史。
    rules_resp = post(c, "/admin/homework-review-rules/list", token=admin)
    rule_data = rules_resp.get("data") or {}
    rules = rule_data.get("list")
    rules_ok = (rules_resp.get("code") == 0 and isinstance(rules, list)
                and rule_data.get("total") == len(rules)
                and all(isinstance(x.get("min_score"), int)
                        and isinstance(x.get("points"), int)
                        and isinstance(x.get("enabled"), bool) for x in rules))
    check(rules_ok, "19. 只读获取批改档位", f"code={rules_resp.get('code')}")
    if rules_ok and hid and su and sub.get("code") == 0:
        score, comment = 85, f"验收批改{suffix}"
        matches = [x for x in rules if x["enabled"] and x["min_score"] <= score]
        expected = max(matches, key=lambda x: x["min_score"])["points"] if matches else 0
        review = post(c, "/homework/review", {"homework_id": hid, "student_id": su["id"],
                                               "score": score, "comment": comment}, token=tokens["teacher"])
        data = review.get("data") or {}
        record = data.get("record") or {}
        check(review.get("code") == 0 and record.get("review_score") == score
              and record.get("review_comment") == comment and data.get("points_delta") == expected
              and data.get("awarded_points") == expected,
              "19b. 老师批改及档位积分", f"code={review.get('code')} 期望积分={expected} 实际={data.get('awarded_points')}")
        history = post(c, "/homework/my-list", {"page": 1, "size": 100}, token=tokens["student"])
        history_data = history.get("data") or {}
        item = next((x for x in history_data.get("list", []) if x.get("id") == hid), {})
        my_record = item.get("my_record") or {}
        check(history.get("code") == 0 and my_record.get("student_id") == su["id"]
              and my_record.get("review_score") == score and my_record.get("review_comment") == comment
              and my_record.get("review_points") == expected,
              "19c. 学生历史包含本人批改结果", f"code={history.get('code')} 作业={hid}")
    else:
        check(False, "19b. 老师批改及档位积分", "前置条件失败")
        check(False, "19c. 学生历史包含本人批改结果", "前置条件失败")

    # 11. 日榜/总榜 + my_rank
    rk = post(c, "/points/rank", {"type": "day", "size": 50}, token=tokens["student"])
    mr = rk.get("data", {}).get("my_rank", 0)
    check(isinstance(mr, int), "11. 日榜返回 my_rank", f"my_rank={mr}")
    rk2 = post(c, "/points/rank", {"type": "total", "size": 50}, token=tokens["student"])
    check(rk2.get("code") == 0, "11b. 总榜可查")

    # 使用本次创建成功的文章 ID，绝不按标题查找已有文章。
    read_art = post(c, "/articles/create", {"title": f"阅读验收{suffix}", "content": "x" * 200}, token=tokens["teacher"])
    ar = (read_art.get("data") or {}).get("article", {}).get("id")
    if read_art.get("code") == 0 and ar is not None:
        before_resp = post(c, "/points/summary", token=tokens["student"])
        heartbeats = [post(c, "/articles/heartbeat", {"article_id": ar, "seconds": 300}, token=tokens["student"]) for _ in range(3)]
        after_resp = post(c, "/points/summary", token=tokens["student"])
        before = (before_resp.get("data") or {}).get("total_points")
        after = (after_resp.get("data") or {}).get("total_points")
        check(before_resp.get("code") == 0 and after_resp.get("code") == 0
              and before is not None and before == after
              and all(r.get("code") == 0 for r in heartbeats),
              "12. 挂机不计分", f"积分 {before} → {after}")
    else:
        skip("12. 挂机不计分", f"创建文章失败: {read_art.get('message')}")

    # 13. 家长绑定 + 扣分 + 余额不足
    # 迭代 v2.1：家长注册时已凭绑定码自动绑定，此处校验绑定关系成立
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next(u for u in ul["data"]["list"] if u["username"] == roles["student"])
    kids = post(c, "/parent/children", token=tokens["parent"])
    kid_ids = [k.get("student_id") for k in kids.get("data", {}).get("list", [])]
    check(su["id"] in kid_ids, "13. 家长注册时自动绑定孩子", f"孩子={kid_ids}")

    balance = post(c, "/points/summary", token=tokens["student"]).get("data", {}).get("total_points", 0)
    if balance >= 1:
        consume = post(c, "/parent/consume", {"student_id": su["id"], "item": "验收扣分", "points": 1}, token=tokens["parent"])
        check(consume.get("code") == 0, "13b. 家长扣分成功", f"剩余 {consume.get('data', {}).get('total_points')}")
    else:
        skip("13b. 家长扣分", "测试学生余额不足")
        skip("14. 积分流水", "未执行扣分")
    current = post(c, "/points/summary", token=tokens["student"])
    remaining = (current.get("data") or {}).get("total_points")
    if current.get("code") == 0 and isinstance(remaining, int) and 0 <= remaining < 10000:
        over = post(c, "/parent/consume", {"student_id": su["id"], "item": "验收余额不足", "points": remaining + 1}, token=tokens["parent"])
        check(over.get("code") == 400 and "积分余额不足" in over.get("message", ""),
              "13c. 余额不足拦截", f"code={over.get('code')} {over.get('message', '')}")
    else:
        skip("13c. 余额不足拦截", "余额不可读或无合法范围内的超额值")

    # 14. 积分变动可追溯
    logs = post(c, "/points/log", {"page": 1, "size": 50, "type": "consume"}, token=tokens["student"])
    if balance >= 1:
        check(logs.get("data", {}).get("total", 0) >= 1, "14. 积分变动可在明细追溯",
              f"consume 类型 {logs.get('data', {}).get('total')} 条")

    skip("15. 敏感操作审计日志", "无法通过接口证明日志属于本次操作，不查询本地数据库")

    # 16. 全接口 POST
    # 通过 OpenAPI 检查是否存在非 POST 的业务路由
    spec = httpx.get(f"{BASE}/openapi.json", timeout=10).json()
    bad = []
    for path, ops in spec.get("paths", {}).items():
        if path in ("/homework_api/health", "/homework_api/openapi.json", "/homework_api/docs", "/homework_api/docs/oauth2-redirect", "/homework_api/redoc"):
            continue
        # 迭代 v2.1：/uploads 是静态文件挂载（GET 下载上传/导出的文件），
        # 不是业务接口，不纳入「全 POST」约束
        if path.startswith("/homework_api/uploads"):
            continue
        for method in ops:
            if method.lower() != "post":
                bad.append(f"{method.upper()} {path}")
    check(not bad, "16. 全接口均为 POST", f"非 POST: {bad[:3]}" if bad else "无 GET/PUT/DELETE 业务接口")

    # 17. 迭代 v2.1 新能力
    regen = post(c, "/classes/regenerate-invite", {"class_id": cid}, token=tokens["teacher"])
    check(regen.get("code") == 0 and regen.get("data", {}).get("invite_code"),
          "17. 老师可重新生成班级邀请码", f"新码={regen.get('data', {}).get('invite_code')}")

    regen_b = post(c, "/classes/regenerate-bind-code", {"student_id": su["id"]}, token=tokens["teacher"])
    check(regen_b.get("code") == 0 and regen_b.get("data", {}).get("bind_code"),
          "17b. 老师可重新生成学生绑定码", f"新码={regen_b.get('data', {}).get('bind_code')}")

    # 导出 PDF：使用本次创建的文章
    exp_art = post(c, "/articles/create", {"title": f"验收导出{suffix}", "content": "导出正文"},
                   token=tokens["teacher"])
    exp_id = exp_art.get("data", {}).get("article", {}).get("id")
    exp = (post(c, "/articles/export-pdf", {"article_id": exp_id}, token=tokens["student"])
           if exp_art.get("code") == 0 and exp_id is not None else {"code": -1, "message": "文章创建失败"})
    check(exp.get("code") == 0 and exp.get("data", {}).get("file_url", "").startswith("/uploads/"),
          "17c. 文章可导出 PDF",
          f"code={exp.get('code')} url={exp.get('data', {}).get('file_url')}")

    # 导出文件可访问（静态挂载）
    file_url = exp.get("data", {}).get("file_url", "")
    if file_url:
        fr = httpx.get(f"{BASE}{file_url}", timeout=15)
        check(fr.status_code == 200 and fr.content[:5] == b"%PDF-",
              "17d. 导出文件可通过 /uploads 访问",
              f"status={fr.status_code} type={fr.headers.get('content-type')}")
    else:
        skip("17d. 导出文件可访问", "导出未返回文件地址")

    # 发布 PDF / word 文章（multipart）
    pdf_bytes = _make_pdf()
    pub = c.post(
        f"{BASE}/articles/create-file",
        data={"title": f"验收PDF{suffix}"},
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {tokens['teacher']}"},
    )
    pub_body = pub.json()
    check(pub_body.get("code") == 0 and pub_body.get("data", {}).get("article", {}).get("file_type") == "pdf",
          "17e. 可发布 PDF 文章（服务端抽取正文）",
          f"code={pub_body.get('code')} {pub_body.get('message', '')}")

    return summary()


def summary() -> int:
    passed = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    print(f"\n=== 业务验收：通过 {passed}，失败 {total - passed}，未验证 {len(skipped)} ===")
    failed = [(n, d) for ok, n, d in results if not ok]
    if failed:
        print("\n未通过项：")
        for n, d in failed:
            print(f"  ❌ {n}  {d}")
    return 0 if not failed and not skipped else 1


if __name__ == "__main__":
    # 支持直接执行：python scripts/acceptance_check.py
    sys.exit(main())