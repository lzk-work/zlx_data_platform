"""商品 SKU 匹配逻辑。"""

from __future__ import annotations

from .models import DailyFirstOrderRow, MatchResult, ProductSkuMaster
from .normalizer import build_source_key


def match_product_sku(
    row: DailyFirstOrderRow,
    initial_product: ProductSkuMaster | None,
    source_key_to_product_skus: dict[tuple[str, str], list[str]],
) -> MatchResult:
    """优先根据校正后货源信息确定商品 SKU。"""
    corrected_key = build_source_key(row.corrected_source_url, row.corrected_spec)
    unique_matches = sorted(set(source_key_to_product_skus.get(corrected_key, [])))

    if len(unique_matches) == 1:
        source_consistent = False
        if initial_product is not None:
            initial_key = build_source_key(initial_product.source_url, initial_product.spec)
            source_consistent = initial_key == corrected_key and row.initial_product_sku == unique_matches[0]
        if source_consistent:
            return MatchResult(
                match_type="initial_consistent",
                correct_product_sku=unique_matches[0],
                source_consistent=True,
                message="初始货源与校正后货源一致",
            )
        return MatchResult(
            match_type="source_key_matched",
            correct_product_sku=unique_matches[0],
            source_consistent=False,
            message="校正后货源匹配到唯一商品SKU",
        )
    if not unique_matches:
        return MatchResult(
            match_type="source_key_missing",
            source_consistent=False,
            message="校正后货源在product_source中未匹配到商品SKU",
        )
    return MatchResult(match_type="ambiguous", source_consistent=False, message="校正后货源在product_source中匹配到多个商品SKU")
