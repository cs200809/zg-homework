"""密码哈希工具测试（app.utils.security）。

背景：passlib 1.7.4 + bcrypt 4.x 组合会在加载 bcrypt backend 时打印
「error reading bcrypt version」告警（passlib 读 bcrypt.__about__.__version__，
而 bcrypt 4.1+ 已移除该属性），并把版本记为 '<unknown>' 而启用 $2$ workaround。
passlib 官方已于 2020 年归档，因此改为直接使用 bcrypt 原生库，去掉这层依赖。

注意：告警发生在 backend **加载期**（import / 首次构造 CryptContext），
早于 pytest 的 caplog 生效，因此这里用子进程捕获 stderr 来断言。
"""

import subprocess
import sys
import textwrap

import bcrypt
import pytest

from app.utils.security import hash_password, verify_password


def test_hash_password_returns_bcrypt_hash():
    """哈希结果应为 bcrypt 格式（$2b$ 前缀）。"""
    h = hash_password("test123456")
    assert h.startswith("$2b$"), f"不是 bcrypt 哈希：{h!r}"


def test_verify_password_accepts_correct_password():
    assert verify_password("test123456", hash_password("test123456")) is True


def test_verify_password_rejects_wrong_password():
    assert verify_password("wrong-password", hash_password("test123456")) is False


def test_verify_password_handles_garbage_hash():
    """哈希损坏时应返回 False，而不是抛异常。"""
    assert verify_password("anything", "not-a-valid-hash") is False


def test_verify_password_handles_empty_hash():
    assert verify_password("anything", "") is False


def test_hash_password_produces_distinct_hashes():
    """同一密码两次哈希应不同（salt 生效）。"""
    assert hash_password("same") != hash_password("same")


def test_hash_password_uses_expected_rounds():
    """默认 cost 应为 12（哈希串第 5-6 位）。"""
    h = hash_password("test123456")
    assert h[4:6] == "12", f"rounds 不是 12：{h!r}"


def test_verify_password_supports_legacy_low_cost_hash():
    """应能校验用更低 rounds 生成的既有哈希（历史数据兼容）。"""
    h = bcrypt.hashpw(b"legacy-pass", bcrypt.gensalt(rounds=4)).decode()
    assert verify_password("legacy-pass", h) is True


def test_verify_password_supports_passlib_generated_hash():
    """passlib 生成的既有哈希必须仍可校验（存量用户不能登不了录）。"""
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    h = ctx.hash("test123456")
    assert verify_password("test123456", h) is True
    assert verify_password("wrong", h) is False


def test_import_emits_no_bcrypt_version_warning():
    """导入并使用哈希工具时，不应再出现 passlib 的 bcrypt 版本探测告警。

    这条是本次改动的直接目标：告警噪音会掩盖真正的错误日志。

    在子进程中运行，因为告警发生在 import / backend 加载期，
    同一进程内的 pytest 捕获器来不及生效。
    """
    code = textwrap.dedent(
        """
        import logging
        logging.basicConfig(level=logging.WARNING)
        from app.utils.security import hash_password, verify_password
        h = hash_password("test123456")
        assert verify_password("test123456", h) is True
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    stderr = proc.stderr.lower()
    assert "error reading bcrypt version" not in stderr, (
        f"仍产生 bcrypt 版本告警：\n{proc.stderr}"
    )
    assert "passlib" not in stderr, f"仍依赖 passlib：\n{proc.stderr}"
