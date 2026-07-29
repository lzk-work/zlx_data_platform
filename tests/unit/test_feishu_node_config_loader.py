"""飞书录入节点配置加载器单元测试。"""

from pathlib import Path

from apps.feishu_node_runner.src.config_loader import (
    list_node_codes,
    load_node_bundle,
    summarize_node,
    validate_node_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "configs" / "feishu_nodes"


def test_list_node_codes_includes_product_intake_poc() -> None:
    """验证可以从正式配置目录发现节点。"""
    node_codes = list_node_codes(CONFIG_ROOT)

    assert "product_intake_poc" in node_codes


def test_product_intake_poc_node_bundle_can_be_loaded() -> None:
    """验证可以读取单节点 node.yaml 和三件套配置。"""
    bundle = load_node_bundle(CONFIG_ROOT, "product_intake_poc")

    assert bundle.node_code == "product_intake_poc"
    assert bundle.node_name == "产品录入POC节点"
    assert bundle.enabled is True
    assert bundle.table_mapping["table_code"] == "product_intake_poc"
    assert bundle.writeback["source_table_code"] == "product_intake_poc"
    assert bundle.distribution["source_table_code"] == "product_intake_poc"


def test_product_intake_poc_node_bundle_passes_validation() -> None:
    """验证单节点样例配置通过基础一致性校验。"""
    bundle = load_node_bundle(CONFIG_ROOT, "product_intake_poc")

    assert validate_node_bundle(bundle) == []


def test_product_intake_poc_node_summary_is_readable() -> None:
    """验证节点摘要能展示关键配置数量。"""
    bundle = load_node_bundle(CONFIG_ROOT, "product_intake_poc")
    summary = summarize_node(bundle)

    assert summary["node_code"] == "product_intake_poc"
    assert summary["biz_table"] == "biz.product_intake_poc"
    assert summary["source_app_token_prefix"].endswith("...")
    assert summary["mapping_field_count"] == 5
    assert summary["writeback_field_count"] == 4
    assert summary["distribution_target_count"] == 2
