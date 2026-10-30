"""端到端验收脚本。

对照 PRD 第 12 节验收标准，逐条调用真实接口验证。
用法：
    python zg-tsp-docs/scripts/acceptance_check.py
需要服务端运行在 127.0.0.1:8000。

注：本脚本随 zg-tsp-docs 仓库分发，会定位同级的 zg-tsp-server 仓库；
若未检出到同级目录，自动重置 admin 密码的兜底逻辑会跳过。
"""

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
SUFFIX = str(int(time.time()))[-6:]

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""))


def post(c: httpx.Client, path: str, body=None, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = c.post(f"{BASE}{path}", json=body or {}, headers=headers)
    try:
        return r.json()
    except Exception:
        return {"code": -1, "message": r.text[:120]}


ADMIN_PASSWORDS = ["admin_demo_123", "admin_demo_1234", "test123456", "admin123456"]


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
    """确保能以 admin 登录。

    优先用已知密码；都不行则直接改库重置（仅限本地开发库）。
    """
    for pwd in ADMIN_PASSWORDS:
        r = post(c, "/auth/login", {"username": "admin", "password": pwd})
        if r.get("code") == 0:
            return r["data"]["token"]

    # 兜底：直接改库（脚本与 zg-tsp-server 同仓库，可直接 import app.*）
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "zg-tsp-server"))
        from app.db.repo import Repo
        from app.db.session import SessionLocal
        from app.utils.security import hash_password

        db = SessionLocal()
        try:
            a = Repo(db).get_user_by_username("admin")
            if a is None:
                return None
            a.password_hash = hash_password(ADMIN_PASSWORDS[0])
            a.must_change_password = False
            a.status = "active"
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"自动重置 admin 密码失败：{e}")
        return None

    r = post(c, "/auth/login", {"username": "admin", "password": ADMIN_PASSWORDS[0]})
    return r.get("data", {}).get("token")


def main() -> int:
    c = httpx.Client(timeout=30)
    suffix = SUFFIX

    # ---------- 前置：确保 admin 可登录 ----------
    admin = _ensure_admin_login(c)
    if admin is None:
        print("无法以 admin 登录，且无法自动重置密码。")
        print("请手动执行：")
        print("  cd zg-tsp-server && python -c \"")
        print("  from app.db.repo import Repo; from app.db.session import SessionLocal")
        print("  from app.utils.security import hash_password")
        print("  db = SessionLocal(); a = Repo(db).get_user_by_username('admin')")
        print("  a.password_hash = hash_password('admin_demo_123')")
        print("  a.must_change_password = False; a.status = 'active'; db.commit()\"")
        return 2

    def admin_reset_pwd(username: str, pwd: str) -> str | None:
        """admin 重置用户密码并清掉强制改密标记，返回可直接登录的 token。

        重置接口返回随机临时密码（PRD 5.8.2），因此需要：
        1. 调 reset-password 拿临时密码
        2. 用临时密码登录（接口会置 must_change_password）
        3. 调 change-password 改密，同时清除强制标记
        4. 用新密码重新登录，拿到干净 token
        """
        lst = post(c, "/admin/users/list", {"keyword": username, "size": 5}, token=admin)
        uid = next((u["id"] for u in lst.get("data", {}).get("list", [])
                    if u["username"] == username), None)
        if uid is None:
            return None

        rst = post(c, "/admin/users/reset-password", {"user_id": uid}, token=admin)
        temp = rst.get("data", {}).get("temp_password")
        if not temp:
            return None

        tk = post(c, "/auth/login", {"username": username, "password": temp})
        if tk.get("code") != 0:
            return None
        temp_token = tk["data"]["token"]

        chg = post(c, "/auth/change-password",
                   {"old_password": temp, "new_password": pwd}, token=temp_token)
        if chg.get("code") != 0:
            return None

        fin = post(c, "/auth/login", {"username": username, "password": pwd})
        return fin.get("data", {}).get("token")

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

    # 1a. 老师注册（一码一用）
    r = post(c, "/auth/register", {
        "username": roles["teacher"], "password": "test123456", "role": "teacher",
        "teacher_invite_code": codes[0],
    })
    check(r.get("code") == 0, "1. 老师可注册", f"code={r.get('code')} {r.get('message', '')}")

    # admin 登录
    r = post(c, "/auth/login", {"username": "admin", "password": "admin_demo_123"})
    check(r.get("code") == 0, "1b. admin 可登录")

    # 重置密码确保可登录
    tokens = {}
    tokens["teacher"] = admin_reset_pwd(roles["teacher"], "test123456") or ""

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
    tokens["student"] = admin_reset_pwd(roles["student"], "test123456") or ""

    # 家长凭学生绑定码注册（自动绑定）
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next((u for u in ul.get("data", {}).get("list", []) if u["username"] == roles["student"]), None)
    r = post(c, "/auth/register", {
        "username": roles["parent"], "password": "test123456", "role": "parent",
        "bind_code": (su or {}).get("bind_code"),
    })
    check(r.get("code") == 0, "1d. 家长可注册（带学生绑定码）",
          f"code={r.get('code')} {r.get('message', '')}")
    tokens["parent"] = admin_reset_pwd(roles["parent"], "test123456") or ""

    login_ok = all(tokens.values())
    login_detail = "teacher/student/parent" if login_ok else "有角色重置密码后仍无法登录"
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
    check(r1.get("code") == 0 and r2.get("code") == 400,
          "2. 老师邀请码一码一用", f"首次={r1.get('code')} 二次={r2.get('code')}")

    r = post(c, "/auth/register", {
        "username": _phone(7), "password": "test123456",
        "role": "teacher", "teacher_invite_code": "INVALID1",
    })
    check(r.get("code") == 400, "2b. 无效邀请码被拒")

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
    target = next((i for i in lst.get("data", {}).get("list", []) if i["code"] == new_codes[0]), None)
    rev = post(c, "/admin/invite/revoke", {"code_id": target["id"]}, token=admin) if target else {"code": -1}
    check(len(new_codes) == 5 and rev.get("code") == 0,
          "3. admin 批量生成/撤销邀请码", f"生成{len(new_codes)}个，撤销={rev.get('code')}")

    # 4. admin 禁用立即生效
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next((u for u in ul.get("data", {}).get("list", []) if u["username"] == roles["student"]), None)
    if su:
        post(c, "/admin/users/disable", {"user_id": su["id"]}, token=admin)
        r = post(c, "/auth/me", token=tokens["student"])
        disabled_now = r.get("code") == 403
        r = post(c, "/auth/login", {"username": roles["student"], "password": "test123456"})
        login_blocked = r.get("code") == 403
        post(c, "/admin/users/enable", {"user_id": su["id"]}, token=admin)
        r = post(c, "/auth/login", {"username": roles["student"], "password": "test123456"})
        check(disabled_now and login_blocked and r.get("code") == 0,
              "4. 禁用后立即无法登录与调用接口", f"接口={disabled_now} 登录={login_blocked} 恢复={r.get('code')==0}")
    else:
        check(False, "4. 禁用立即生效", "未找到学生账号")

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
    check(r.get("code") == 400, "18b. 改密：新密码短于 6 位被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18c. 新旧密码相同被拒
    r = post(c, "/auth/change-password",
             {"old_password": old_pwd, "new_password": old_pwd},
             token=tokens["student"])
    check(r.get("code") == 400 and "不能与原密码相同" in r.get("message", ""),
          "18c. 改密：新旧密码相同被拒",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18d. 原密码正确时改密成功
    r = post(c, "/auth/change-password",
             {"old_password": old_pwd, "new_password": new_pwd},
             token=tokens["student"])
    check(r.get("code") == 0, "18d. 改密：原密码正确时改密成功",
          f"code={r.get('code')} {r.get('message', '')}")

    # 18e. 新密码可登录
    login_new = post(c, "/auth/login", {"username": roles["student"], "password": new_pwd})
    check(login_new.get("code") == 0, "18e. 改密：新密码可登录",
          f"code={login_new.get('code')} {login_new.get('message', '')}")

    # 18f. 旧密码失效
    login_old = post(c, "/auth/login", {"username": roles["student"], "password": old_pwd})
    check(login_old.get("code") == 400, "18f. 改密：旧密码登录失效",
          f"code={login_old.get('code')}")

    # 18g. 改回原密码（JWT 无状态，原 token 仍可用）
    back = post(c, "/auth/change-password",
                {"old_password": new_pwd, "new_password": old_pwd},
                token=tokens["student"])
    check(back.get("code") == 0, "18g. 改密：可改回原密码（测试数据复原）",
          f"code={back.get('code')} {back.get('message', '')}")

    # 5. admin 无法禁用 admin
    r = post(c, "/admin/users/disable", {"user_id": 1}, token=admin)
    check(r.get("code") == 400, "5. admin 无法禁用 admin（含自己）", f"code={r.get('code')}")

    # 6. 修改积分规则立即生效
    post(c, "/admin/rules/update", {"rule_key": "checkin_daily", "points": 77, "daily_limit": 1}, token=admin)
    stu_ids = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    sid = stu_ids["data"]["list"][0]["id"]
    ci = post(c, "/checkin/do", token=tokens["student"])
    got = ci.get("data", {}).get("points")
    check(got == 77, "6. 改规则后新发放立即按新值", f"签到得 {got} 分（规则设为 77）")
    # 禁用规则不发
    post(c, "/admin/rules/update", {"rule_key": "checkin_daily", "enabled": False}, token=admin)
    # 换个学生测禁用
    s2 = _phone(4)
    post(c, "/auth/register", {"username": s2, "password": "test123456",
                               "role": "student", "class_invite_code": class_invite})
    tok2 = post(c, "/auth/login", {"username": s2, "password": "test123456"})["data"]["token"]
    ci2 = post(c, "/checkin/do", token=tok2)
    check(ci2.get("data", {}).get("points") == 0, "6b. 禁用规则不发放",
          f"得到 {ci2.get('data', {}).get('points')}")
    post(c, "/admin/rules/update", {"rule_key": "checkin_daily", "enabled": True, "points": 5, "daily_limit": 1}, token=admin)

    # 7. 文章管理权限
    art = post(c, "/articles/create", {"title": f"验收文章{suffix}", "content": "正文"}, token=admin)
    aid = art.get("data", {}).get("article", {}).get("id")
    teacher_list = post(c, "/articles/records", {"article_id": aid}, token=tokens["teacher"])
    check(teacher_list.get("code") == 403, "7. 老师仅能管自己的文章",
          f"老师查 admin 文章 code={teacher_list.get('code')}")
    d = post(c, "/articles/delete", {"article_id": aid}, token=admin)
    check(d.get("code") == 0, "7b. admin 可删除任意文章")

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
    post(c, "/admin/rules/update", {"rule_key": "homework_on_time", "points": 10, "enabled": True}, token=admin)
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

    # 10. 积分正确且受日上限约束
    pts = sub.get("data", {}).get("record", {}).get("points")
    check(pts == 10, "10. 按时提交发 10 分", f"实得 {pts}")

    # 11. 日榜/总榜 + my_rank
    rk = post(c, "/points/rank", {"type": "day", "size": 50}, token=tokens["student"])
    mr = rk.get("data", {}).get("my_rank", 0)
    check(isinstance(mr, int), "11. 日榜返回 my_rank", f"my_rank={mr}")
    rk2 = post(c, "/points/rank", {"type": "total", "size": 50}, token=tokens["student"])
    check(rk2.get("code") == 0, "11b. 总榜可查")

    # 12. 阅读挂机不计分
    post(c, "/articles/create", {"title": f"阅读验收{suffix}", "content": "x" * 200}, token=tokens["teacher"])
    alist = post(c, "/articles/list", {"page": 1, "size": 50}, token=tokens["student"])
    aids = [a for a in alist.get("data", {}).get("list", []) if a["title"] == f"阅读验收{suffix}"]
    if aids:
        ar = aids[0]["id"]
        before = post(c, "/points/summary", token=tokens["student"]).get("data", {}).get("total_points", 0)
        for _ in range(3):
            post(c, "/articles/heartbeat", {"article_id": ar, "seconds": 300}, token=tokens["student"])
        after = post(c, "/points/summary", token=tokens["student"]).get("data", {}).get("total_points", 0)
        check(before == after, "12. 挂机不计分", f"挂机3次后积分 {before} → {after}")

    # 13. 家长绑定 + 扣分 + 余额不足
    # 迭代 v2.1：家长注册时已凭绑定码自动绑定，此处校验绑定关系成立
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next(u for u in ul["data"]["list"] if u["username"] == roles["student"])
    kids = post(c, "/parent/children", token=tokens["parent"])
    kid_ids = [k.get("student_id") for k in kids.get("data", {}).get("list", [])]
    check(su["id"] in kid_ids, "13. 家长注册时自动绑定孩子", f"孩子={kid_ids}")

    consume = post(c, "/parent/consume", {"student_id": su["id"], "item": "看手机", "points": 3}, token=tokens["parent"])
    check(consume.get("code") == 0, "13b. 家长扣分成功", f"剩余 {consume.get('data', {}).get('total_points')}")
    over = post(c, "/parent/consume", {"student_id": su["id"], "item": "买玩具", "points": 99999}, token=tokens["parent"])
    check(over.get("code") == 400, "13c. 余额不足拦截", f"code={over.get('code')}")

    # 14. 积分变动可追溯
    logs = post(c, "/points/log", {"page": 1, "size": 50, "type": "consume"}, token=tokens["student"])
    check(logs.get("data", {}).get("total", 0) >= 1, "14. 积分变动可在明细追溯",
          f"consume 类型 {logs.get('data', {}).get('total')} 条")

    # 15. 审计日志
    from app.db.repo import Repo
    from app.db.session import SessionLocal
    from app.models.entities import AdminLog
    from sqlalchemy import select

    db = SessionLocal()
    try:
        acts = set(db.scalars(select(AdminLog.action)).all())
    finally:
        db.close()
    need = {"user_disable", "rule_update", "idiom_import", "invite_create"}
    check(need <= acts, "15. 敏感操作有审计日志", f"已记录: {sorted(a for a in acts if a in need)}")

    # 16. 全接口 POST
    # 通过 OpenAPI 检查是否存在非 POST 的业务路由
    spec = httpx.get(f"{BASE}/openapi.json", timeout=10).json()
    bad = []
    for path, ops in spec.get("paths", {}).items():
        if path in ("/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue
        # 迭代 v2.1：/uploads 是静态文件挂载（GET 下载上传/导出的文件），
        # 不是业务接口，不纳入「全 POST」约束
        if path.startswith("/uploads"):
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

    # 导出 PDF：单独建一篇文章（7b 步已把 aid 那篇删了）
    exp_art = post(c, "/articles/create", {"title": f"验收导出{suffix}", "content": "导出正文"},
                   token=tokens["teacher"])
    exp_id = exp_art.get("data", {}).get("article", {}).get("id")
    exp = post(c, "/articles/export-pdf", {"article_id": exp_id}, token=tokens["student"])
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
    print(f"\n=== 业务验收：{passed}/{total} 通过 ===")
    failed = [(n, d) for ok, n, d in results if not ok]
    if failed:
        print("\n未通过项：")
        for n, d in failed:
            print(f"  ❌ {n}  {d}")
    return 0 if not failed else 1


if __name__ == "__main__":
    # 支持直接执行：python scripts/acceptance_check.py
    # 需要能 import app.*，故把 zg-tsp-server 加入 sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "zg-tsp-server"))
    sys.exit(main())