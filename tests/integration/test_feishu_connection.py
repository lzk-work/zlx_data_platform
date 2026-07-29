"""Feishu integration checks.

These tests call real Feishu OpenAPI endpoints. They are opt-in so normal test
runs do not depend on network access or valid local secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.feishu_intake_poc.src.settings import load_env_file, load_settings
from connectors.feishu import FeishuClient, FeishuConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV_PATH = PROJECT_ROOT / "apps" / "feishu_intake_poc" / "config" / "test.env"

# 真实飞书连接测试开关。
# POC 阶段默认开启，方便在 PyCharm 中直接点击单个测试函数。
# 如需临时关闭真实外部调用，改为 False。
RUN_FEISHU_CONNECTION_TESTS_IN_CODE = True


def integration_enabled() -> bool:
    return RUN_FEISHU_CONNECTION_TESTS_IN_CODE or os.getenv("RUN_FEISHU_INTEGRATION_TESTS") == "1"


pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        not integration_enabled(),
        reason="Set RUN_FEISHU_CONNECTION_TESTS_IN_CODE=True or RUN_FEISHU_INTEGRATION_TESTS=1.",
    ),
]


def test_feishu_app_credentials_can_get_tenant_access_token() -> None:
    """Verify app_id/app_secret can obtain a tenant_access_token.

    The test intentionally never prints or asserts the full token value.
    """
    load_env_file(TEST_ENV_PATH)

    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]

    with FeishuClient(FeishuConfig(app_id=app_id, app_secret=app_secret)) as client:
        status = client.health_check()

    assert status["ok"] is True
    assert status["tenant_access_token_prefix"].startswith("t-")

def test_feishu_bitable_fields_can_be_listed() -> None:
    """验证可以读取节点来源多维表字段结构，并打印字段信息供人工核对。"""
    settings = load_settings(TEST_ENV_PATH)

    with FeishuClient.from_settings(settings) as client:
        fields = client.list_bitable_fields(
            app_token=settings.feishu_app_token,
            table_id=settings.feishu_table_id,
        )

    print("\n飞书多维表格字段列表：")
    for index, field in enumerate(fields, start=1):
        field_name = field.get("field_name")
        field_id = field.get("field_id")
        field_type = field.get("type")
        print(f"{index}. name={field_name} | id={field_id} | type={field_type}")

    assert fields
    assert all("field_id" in field for field in fields)
    assert all("field_name" in field for field in fields)
