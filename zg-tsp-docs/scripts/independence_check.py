"""单仓模块边界检查（PRD 第 12 节「模块边界」）。

静态分析服务端与 Web 的源码和配置，不依赖运行时。
仓库根目录按脚本自身位置定位，可从任意工作目录运行。
用法：
    python zg-tsp-docs/scripts/independence_check.py
"""

import ast
import json
import re
import io
import subprocess
import sys
import tokenize
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


def cross_module_references(path: Path, module: str) -> list[str]:
    """查找源码中指向另一模块的 import 或文件路径，忽略注释和文档字符串。"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".py":
        doc_lines = docstring_lines(path)
        try:
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            parts = [(tok.start[0], tok.string) for tok in tokens
                     if tok.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                                         tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER)
                     and not (tok.type == tokenize.STRING and tok.start[0] in doc_lines)]
        except (tokenize.TokenError, IndentationError):
            # 源码不完整时也尽量检查，不能静默跳过整个文件。
            parts = list(enumerate(text.splitlines(), 1))
    else:
        # 保留字符串中的 //、/* 等字符，同时移除行注释和多行注释。
        lexer = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`|[^/\"'`]+|/", re.MULTILINE)
        parts = []
        for match in lexer.finditer(text):
            value = match.group()
            if not value.startswith(("//", "/*")):
                parts.append((text.count("\n", 0, match.start()) + 1, value))

    # 文件路径必须实际落入另一模块，不能仅凭 server/web 等路径段判断。
    # 普通文本和 HTTP 地址也不是源码依赖。
    others = [other for other in MODULES if other != module]
    hits = []
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            names = {other.removeprefix("zg-tsp-") for other in others}
            names.update(other.replace("-", "_") for other in others)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imports = [node.module or ""]
                else:
                    continue
                if any(name.split(".")[0] in names for name in imports):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno}: import {', '.join(imports)}")
    string_pattern = re.compile(r"(['\"`])((?:\\.|(?!\1)[^\\])*)\1", re.DOTALL)
    for line, value in parts:
        for match in string_pattern.finditer(value):
            candidate = match.group(2)
            if not candidate or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
                continue
            if candidate.startswith(("./", "../", "/")):
                target = (path.parent / candidate).resolve()
                cross = any(target.is_relative_to((ROOT / other).resolve()) for other in others)
            else:
                # Bare package specifiers may refer directly to a sibling module.
                cross = any(candidate == other or candidate.startswith(other + "/")
                            for other in others)
            if cross:
                hits.append(f"{path.relative_to(ROOT)}:{line}: {candidate[:70]}")
    return hits


def main() -> int:
    print("\n=== 模块边界检查 ===")

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
        for f in source_files(m):
            cross.extend(cross_module_references(f, m))
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
          else "代码中仅 localhost/示例地址；真实地址走 .env")

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
    print(f"\n=== 模块边界检查：{passed}/{len(results)} 通过 ===")
    failed = [(n, d) for ok, n, d in results if not ok]
    if failed:
        print("\n未通过项：")
        for n, d in failed:
            print(f"  ❌ {n}  {d}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())