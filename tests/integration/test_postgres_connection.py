"""PostgreSQL 真实连接测试。

这些测试会连接真实数据库。是否执行由 RUN_POSTGRES_CONNECTION_TESTS_IN_CODE
控制；环境变量 RUN_POSTGRES_INTEGRATION_TESTS=1 保留为命令行备用方式。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.feishu_intake_poc.src.settings import load_env_file
from connectors.database.postgres import PostgresClient, PostgresConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV_PATH = PROJECT_ROOT / "apps" / "feishu_intake_poc" / "config" / "test.env"

# 真实 PostgreSQL 连接测试开关。
# POC 阶段默认开启，方便在 PyCharm 中直接点击单个测试函数。
# 如需临时关闭真实外部调用，改为 False。
RUN_POSTGRES_CONNECTION_TESTS_IN_CODE = True


def integration_enabled() -> bool:
    """判断是否允许执行 PostgreSQL 真实连接测试。"""
    return RUN_POSTGRES_CONNECTION_TESTS_IN_CODE or os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") == "1"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        not integration_enabled(),
        reason="Set RUN_POSTGRES_CONNECTION_TESTS_IN_CODE=True or RUN_POSTGRES_INTEGRATION_TESTS=1.",
    ),
]


def test_postgres_database_url_can_connect() -> None:
    """验证 DATABASE_URL 可以连接数据库，并返回当前库名和用户。"""
    load_env_file(TEST_ENV_PATH)

    database_url = os.environ["DATABASE_URL"]
    client = PostgresClient(PostgresConfig(database_url=database_url))

    status = client.health_check()

    assert status["ok"] is True
    assert status["database_name"]
    assert status["user_name"]
