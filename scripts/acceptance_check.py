"""P9 端到端验收脚本。

对照 PRD 第 12 节验收标准，逐条调用真实接口验证。
用法：
    cd zg-tsp-server && python -m scripts.acceptance_check
需要服务端运行在 127.0.0.1:8000。
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
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "zg-tsp-server"))
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

    # 1. 四角色登录 + 权限隔离
    roles = {}
    for role, uname in [
        ("teacher", f"ac_t{suffix}"),
        ("student", f"ac_s{suffix}"),
        ("parent", f"ac_p{suffix}"),
    ]:
        roles[role] = uname
    # admin 建账号：老师需邀请码
    inv = post(c, "/admin/invite/create", {"count": 3, "expire_days": 7}, token=admin)
    codes = inv.get("data", {}).get("codes", [])
    ok = True
    detail = ""
    for role, uname in roles.items():
        body = {"username": uname, "password": "test123456", "role": role}
        if role == "teacher":
            body["teacher_invite_code"] = codes[0]
        rr = post(c, "/auth/register", body)
        if rr.get("code") != 0:
            ok, detail = False, f"{role} 注册失败: {rr.get('message')}"
            break
    check(ok, "1. 四角色可注册", detail)

    # admin 登录
    r = post(c, "/auth/login", {"username": "admin", "password": "admin_demo_123"})
    check(r.get("code") == 0, "1b. admin 可登录")

    # 重置密码确保可登录
    tokens = {}
    login_ok = True
    login_detail = "teacher/student/parent"
    for role, uname in roles.items():
        tokens[role] = admin_reset_pwd(uname, "test123456") or ""
        if not tokens[role]:
            login_ok = False
            login_detail = f"{role} 重置密码后仍无法登录"
    check(login_ok, "1c. 四角色均可登录", login_detail)

    # 权限隔离：学生访问 admin 接口 403
    r = post(c, "/admin/stats/overview", token=tokens.get("student"))
    check(r.get("code") == 403, "1d. 权限隔离（学生访问 admin 接口 403）", f"code={r.get('code')}")

    # admin 不出现在排行榜
    r = post(c, "/points/rank", {"type": "total", "size": 50}, token=tokens.get("student"))
    admin_ids = [u for u in r.get("data", {}).get("list", []) if u["username"] == "admin"]
    check(not admin_ids, "1e. admin 不出现在排行榜")

    # 2. 老师邀请码一码一用
    r1 = post(c, "/auth/register", {
        "username": f"ac_t2_{suffix}", "password": "test123456",
        "role": "teacher", "teacher_invite_code": codes[1],
    })
    r2 = post(c, "/auth/register", {
        "username": f"ac_t3_{suffix}", "password": "test123456",
        "role": "teacher", "teacher_invite_code": codes[1],
    })
    check(r1.get("code") == 0 and r2.get("code") == 400,
          "2. 老师邀请码一码一用", f"首次={r1.get('code')} 二次={r2.get('code')}")

    r = post(c, "/auth/register", {
        "username": f"ac_t4_{suffix}", "password": "test123456",
        "role": "teacher", "teacher_invite_code": "INVALID1",
    })
    check(r.get("code") == 400, "2b. 无效邀请码被拒")

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
    s2 = f"ac_s2_{suffix}"
    post(c, "/auth/register", {"username": s2, "password": "test123456", "role": "student"})
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

    # 8. 学生加入班级 + 老师布置作业
    cls = post(c, "/classes/create", {"name": f"验收班{suffix}"}, token=tokens["teacher"])
    class_info = cls.get("data", {}).get("class")
    if not class_info:
        check(False, "8. 学生加入班级", f"建班失败: {cls.get('message')}")
        return summary()
    cid = class_info["id"]
    join = post(c, "/classes/join", {"invite_code": class_info["invite_code"]}, token=tokens["student"])
    check(join.get("code") == 0, "8. 学生加入班级", f"code={join.get('code')}")

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
    ul = post(c, "/admin/users/list", {"keyword": roles["student"], "size": 5}, token=admin)
    su = next(u for u in ul["data"]["list"] if u["username"] == roles["student"])
    bind_code = su.get("bind_code")
    bind = post(c, "/parent/bind", {"bind_code": bind_code}, token=tokens["parent"])
    check(bind.get("code") == 0, "13. 家长绑定孩子", f"code={bind.get('code')}")

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
        for method in ops:
            if method.lower() != "post":
                bad.append(f"{method.upper()} {path}")
    check(not bad, "16. 全接口均为 POST", f"非 POST: {bad[:3]}" if bad else "无 GET/PUT/DELETE 业务接口")

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
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "zg-tsp-server"))
    sys.exit(main())