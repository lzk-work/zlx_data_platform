"""Source URL cleaner tests."""

import pytest

from apps.product_sku_management.src.constants import (
    SOURCE_PLATFORM_1688,
    SOURCE_PLATFORM_TAOBAO,
    SOURCE_PLATFORM_TMALL,
)
from apps.product_sku_management.src.domain.source_cleaner import clean_source_url


def test_clean_source_url_normalizes_1688_offer_url() -> None:
    cleaned = clean_source_url(
        "https://detail.1688.com/offer/1006973663950.html?offerId=1006973663950&spm=test"
    )

    assert cleaned.source_platform == SOURCE_PLATFORM_1688
    assert cleaned.source_url == "https://detail.1688.com/offer/1006973663950.html"


def test_clean_source_url_normalizes_1688_htm_to_html() -> None:
    cleaned = clean_source_url("https://detail.1688.com/offer/732422103766.htm")

    assert cleaned.source_platform == SOURCE_PLATFORM_1688
    assert cleaned.source_url == "https://detail.1688.com/offer/732422103766.html"


def test_clean_source_url_accepts_1688_offer_url_with_ampersand_after_html() -> None:
    cleaned = clean_source_url("https://detail.1688.com/offer/912495606535.html&wh_cpid=581n3128")

    assert cleaned.source_platform == SOURCE_PLATFORM_1688
    assert cleaned.source_url == "https://detail.1688.com/offer/912495606535.html"


def test_clean_source_url_rejects_incomplete_url() -> None:
    with pytest.raises(ValueError, match="完整"):
        clean_source_url("offer/1006973663950.html")


def test_clean_source_url_keeps_taobao_and_tmall_full_links() -> None:
    taobao_url = "https://item.taobao.com/item.htm?id=123&sku=1"
    tmall_url = "https://detail.tmall.com/item.htm?id=123&sku=1"

    assert clean_source_url(taobao_url).source_platform == SOURCE_PLATFORM_TAOBAO
    assert clean_source_url(taobao_url).source_url == taobao_url
    assert clean_source_url(tmall_url).source_platform == SOURCE_PLATFORM_TMALL
    assert clean_source_url(tmall_url).source_url == tmall_url
