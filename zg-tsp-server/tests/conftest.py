"""pytest 夹具：每个测试用例独立的内存数据。"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.repo import repo  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.initial_data import (  # noqa: E402
    DEV_INVITE_CODE,
    TEST_PASSWORD,
    seed_admin,
    seed_dev_accounts,
    seed_point_rules,
)


@pytest.fixture
def client():
    """干净的 app 实例 + 空内存库。"""
    repo.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(client):
    """含 admin、积分规则、测试账号与邀请码。"""
    admin = seed_admin()
    seed_point_rules()
    seed_dev_accounts(admin.id)
    return client


@pytest.fixture
def invite_code():
    return DEV_INVITE_CODE


@pytest.fixture
def test_password():
    return TEST_PASSWORD