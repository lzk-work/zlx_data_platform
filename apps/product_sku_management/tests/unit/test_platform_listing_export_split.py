"""Platform listing Dianxiaomi export split tests."""

from apps.product_sku_management.src.constants import EXPORT_ACTION_CREATE, EXPORT_ACTION_SKIP, EXPORT_ACTION_UPDATE
from apps.product_sku_management.src.models.output_models import DianxiaomiExportPlan
from apps.product_sku_management.src.workflows.platform_listing_supplement import (
    dianxiaomi_template_path,
    empty_export_buckets,
    plan_with_action_export_file,
)


def test_dianxiaomi_template_path_splits_create_and_update(tmp_path) -> None:
    assert dianxiaomi_template_path(tmp_path, "product_sku", EXPORT_ACTION_CREATE).name == "dianxiaomi_product_sku_create.xlsx"
    assert dianxiaomi_template_path(tmp_path, "bundle_sku", EXPORT_ACTION_UPDATE).name == "dianxiaomi_bundle_sku_update.xlsx"
    assert dianxiaomi_template_path(tmp_path, "platform_pair", EXPORT_ACTION_CREATE).name == "dianxiaomi_platform_pair_create.xlsx"


def test_plan_with_action_export_file_keeps_skip_empty_and_routes_update(tmp_path) -> None:
    skipped = DianxiaomiExportPlan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_1",
        action_type=EXPORT_ACTION_SKIP,
        reason="unchanged",
        current_hash="hash_1",
        previous_hash="hash_1",
        payload_json={},
        export_file="",
    )
    updated = DianxiaomiExportPlan(
        process_batch_id="batch_1",
        object_type="product_sku",
        object_key="YS_2",
        action_type=EXPORT_ACTION_UPDATE,
        reason="changed",
        current_hash="hash_2",
        previous_hash="hash_1",
        payload_json={},
        export_file="old.xlsx",
    )

    assert plan_with_action_export_file(skipped, tmp_path, "product_sku").export_file == ""
    assert plan_with_action_export_file(updated, tmp_path, "product_sku").export_file.endswith(
        "dianxiaomi_product_sku_update.xlsx",
    )


def test_empty_export_buckets_has_create_and_update_only() -> None:
    buckets = empty_export_buckets()

    assert set(buckets) == {EXPORT_ACTION_CREATE, EXPORT_ACTION_UPDATE}
    assert buckets[EXPORT_ACTION_CREATE] == []
    assert buckets[EXPORT_ACTION_UPDATE] == []
