"""邀请码 / 绑定码生成（PRD 5.1、5.2）。

班级邀请码与学生绑定码的生成逻辑集中在此，
避免 auth.py / classes.py 各自维护一份导致字符集不一致。
"""

import secrets
import string

# 班级邀请码：去掉易混淆字符（0/O、1/I）
CLASS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# 学生绑定码：大写字母 + 数字
BIND_CODE_ALPHABET = string.ascii_uppercase + string.digits


def gen_class_code(length: int = 6) -> str:
    """生成班级邀请码（默认 6 位）。"""
    return "".join(secrets.choice(CLASS_CODE_ALPHABET) for _ in range(length))


def gen_bind_code(length: int = 8) -> str:
    """生成学生绑定码（默认 8 位，家长凭此绑定孩子）。"""
    return "".join(secrets.choice(BIND_CODE_ALPHABET) for _ in range(length))
