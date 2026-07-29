"""配置读取工具的单元测试。"""

import os
from pathlib import Path

from apps.feishu_intake_poc.src.settings import load_env_file, load_settings
from apps.feishu_intake_poc.src.settings import normalize_env_value


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NODE_CONFIG_ROOT = PROJECT_ROOT / "configs" / "feishu_nodes"


def test_normalize_env_value_keeps_inner_quotes() -> None:
    value = 'CurrentValue.[开发状态]="已完成"'

    assert normalize_env_value(value) == value


def test_normalize_env_value_strips_wrapping_quotes_only() -> None:
    value = '"CurrentValue.[开发状态]=\\"已完成\\""'

    assert normalize_env_value(value) == 'CurrentValue.[开发状态]=\\"已完成\\"'


def test_load_settings_can_use_node_config(tmp_path) -> None:
    """验证来源多维表参数从 node.yaml 读取，默认选择第一个启用任务。"""
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "FEISHU_APP_ID=test_app_id",
                "FEISHU_APP_SECRET=test_app_secret",
                "DATABASE_URL=postgresql://user:pass@localhost:5432/test",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_path, node_code="product_intake_poc", node_config_root=NODE_CONFIG_ROOT)

    assert settings.node_code == "product_intake_poc"
    assert settings.feishu_app_token == "YCw0bxHEDah4YZsonzZc5pJsn8j"
    assert settings.feishu_table_id == "tbleu4APzm8lD3Ke"
    assert settings.mapping_path == NODE_CONFIG_ROOT / "product_intake_poc" / "table_mapping.yaml"
    assert settings.task_code == "incremental"
    assert settings.feishu_read_filter
    assert settings.feishu_read_filter["conditions"][0]["field"] == "开发状态"


def test_load_settings_can_select_named_node_task(tmp_path) -> None:
    """验证可以显式选择节点中的某个任务。"""
    env_path = tmp_path / "test.env"
    env_path.write_text(
        "\n".join(
            [
                "FEISHU_APP_ID=test_app_id",
                "FEISHU_APP_SECRET=test_app_secret",
                "DATABASE_URL=postgresql://user:pass@localhost:5432/test",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        env_path,
        node_code="product_intake_poc",
        node_config_root=NODE_CONFIG_ROOT,
        task_code="reconcile",
    )

    assert settings.task_code == "reconcile"
    assert settings.feishu_read_filter
    assert settings.feishu_read_filter["conditions"][1]["value"] == "-3d"


def test_load_env_file_strips_utf8_bom_from_first_key(tmp_path, monkeypatch) -> None:
    """验证 Windows UTF-8 BOM 不会污染第一行环境变量 key。"""
    monkeypatch.delenv("FEISHU_NODE_CODE", raising=False)
    env_path = tmp_path / "bom.env"
    env_path.write_text("\ufeffFEISHU_NODE_CODE=product_intake_poc", encoding="utf-8")

    load_env_file(env_path)

    assert os.environ["FEISHU_NODE_CODE"] == "product_intake_poc"