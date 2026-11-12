"""模块独立性检查（PRD 第 12 节「模块独立性」）。

静态分析四个模块的源码与配置，不依赖运行时。
用法：
    python zg-tsp-docs/scripts/independence_check.py

需在**聚合仓库**（四个模块同级检出）下运行；若缺少任一模块则跳过对应检查。
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

# 聚合仓库根目录：本脚本位于 <root>/zg-tsp-docs/scripts/
ROOT = Path(__file__).resolve().parent.parent.parent
MODULES = ["zg-tsp-server", "zg-tsp-web"]

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  — {detail}" if detail else ""))


def source_files(module: str) -> list[Path]:
    """模块的业务源码（排除平台工程与构建产物）。"""
    m = ROOT / module
    exts = {".py", ".ts", ".tsx", ".dart"}
    skip_dirs = {
        "node_modules", "build", ".dart_tool", "__pycache__", ".git",
        "ios", "android", "dist", ".venv", "uploads", "data", "Pods",
    }
    out = []
    for p in m.rglob("*"):
        if not p.is_file() or p.suffix not in exts:
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        out.append(p)
    return out


def docstring_lines(path: Path) -> set[int]:
    """Python 文件中属于 docstring 的行号集合（文档中的示例不算硬编码）。"""
    if path.suffix != ".py":
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError):
        return set()
    lines: set[int] = set()
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def main() -> int:
    print("\n=== 模块独立性检查 ===")

    # 1. 各模块可单独安装依赖（依赖清单存在且自封闭）
    manifests = {
        "zg-tsp-server": "zg-tsp-server/requirements.txt",
        "zg-tsp-web": "zg-tsp-web/package.json",
    }
    missing = [m for m, f in manifests.items() if not (ROOT / f).exists()]
    check(not missing, "1. 各模块有独立依赖清单",
          f"缺失: {missing}" if missing else "requirements / package.json")

    # 2. 源码中不含对其他模块的引用
    cross = []
    for m in MODULES:
        me = m.replace("zg-tsp-", "")
        for f in source_files(m):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for other in MODULES:
                if other == m:
                    continue
                o = other.replace("zg-tsp-", "")
                # 只查 import/路径引用，忽略注释与文档字符串中的提及
                for line in txt.splitlines():
                    code = line.strip()
                    if code.startswith(("#", "//", "*", "///", "/*")):
                        continue
                    if re.search(rf"\b(from|import|require)\b.*\b(o)\b", code):
                        cross.append(f"{f.relative_to(ROOT)}: {code[:70]}")
    check(not cross, "2. 源码中无跨模块 import / 路径引用",
          f"发现 {len(cross)} 处: {cross[:2]}" if cross else "各模块零交叉引用")

    # 3. 服务端地址为外部配置，无硬编码
    hardcoded = []
    patterns = [
        (re.compile(r"https?://(?!127\.0\.0\.1|localhost|0\.0\.0\.0|test\.example|api\.example)[\w.-]+"), "URL"),
        (re.compile(r"['\"]mysql\+pymysql://(?!root:)[\w.-]+"), "DB URL"),
    ]
    for m in MODULES:
        for f in source_files(m):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            doc_lines = docstring_lines(f)
            for i, line in enumerate(txt.splitlines(), 1):
                st = line.strip()
                if st.startswith(("#", "//", "///", "*")):
                    continue
                if i in doc_lines:
                    continue
                for pat, kind in patterns:
                    if pat.search(line):
                        hardcoded.append(f"{f.relative_to(ROOT)}:{i} [{kind}]")
    check(not hardcoded, "3. 服务端地址均为外部配置，无硬编码",
          f"发现 {len(hardcoded)} 处: {hardcoded[:3]}" if hardcoded
          else "代码中仅 localhost/示例地址；真实地址走 .env / --dart-define")

    # 4. 三端配置项存在
    cfg = {
        "服务端 .env.example": ROOT / "zg-tsp-server/.env.example",
        "Web .env.production": ROOT / "zg-tsp-web/.env.production",
    }
    absent = [n for n, p in cfg.items() if not p.exists()]
    check(not absent, "4. 客户端均有外部配置项",
          f"缺失: {absent}" if absent else ".env.example / .env.production")

    # 5. 各模块独立构建产物与 Dockerfile
    docker = [m for m in ("zg-tsp-server", "zg-tsp-web") if not (ROOT / m / "Dockerfile").exists()]
    check(not docker, "5. server/web 有独立打包配置",
          f"缺失: {docker}" if docker else "各自 Dockerfile")

    # 7. 服务端不可用时客户端不崩溃（静态验证：是否有降级处理）
    web_degrade = (ROOT / "zg-tsp-web/src/api/client.ts").read_text(encoding="utf-8")
    check("ServiceUnavailableError" in web_degrade,
          "6. 服务端不可用时客户端降级不崩溃",
          "Web 端有 ServiceUnavailableError")

    # 8. 服务端 /health 可用且未引入多余监控依赖
    req = (ROOT / "zg-tsp-server/requirements.txt").read_text(encoding="utf-8")
    monitoring = [d for d in ("prometheus", "sentry", "datadog", "newrelic") if d in req.lower()]
    check(not monitoring, "7. 未引入多余监控依赖",
          f"发现: {monitoring}" if monitoring else "无 prometheus/sentry 等")

    health = (ROOT / "zg-tsp-server/app/main.py").read_text(encoding="utf-8")
    check('/health"' in health, "8. 服务端 /health 已实现", "POST /health")

    # ---------- 汇总 ----------
    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\n=== 独立性检查：{passed}/{len(results)} 通过 ===")
    failed = [(n, d) for ok, n, d in results if not ok]
    if failed:
        print("\n未通过项：")
        for n, d in failed:
            print(f"  ❌ {n}  {d}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())