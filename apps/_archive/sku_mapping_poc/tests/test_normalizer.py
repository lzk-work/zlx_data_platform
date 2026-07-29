from __future__ import annotations

from apps.sku_mapping_poc.src.normalizer import build_source_key, clean_source_url, clean_spec


def test_clean_1688_single_url() -> None:
    raw = " https://detail.1688.com/offer/966301241755.html?spm=a26352.b28411319/2508.0.0 "

    assert clean_source_url(raw) == "https://detail.1688.com/offer/966301241755.html"


def test_clean_1688_multi_url_keeps_first_seen_order() -> None:
    raw = (
        "https://detail.1688.com/offer/111.html?x=1 "
        "https://detail.1688.com/offer/222.html "
        "https://detail.1688.com/offer/111.html?x=2"
    )

    assert clean_source_url(raw) == (
        "货源1:https://detail.1688.com/offer/111.html\n"
        "货源2:https://detail.1688.com/offer/222.html"
    )


def test_clean_taobao_and_tmall_url() -> None:
    assert clean_source_url("https://item.taobao.com/item.htm?id=123&skuId=456&x=1") == (
        "https://item.taobao.com/item.htm?id=123&skuId=456"
    )
    assert clean_source_url("https://detail.tmall.com/item.htm?id=789") == "https://detail.tmall.com/item.htm?id=789"


def test_unknown_source_url_returns_empty() -> None:
    assert clean_source_url("https://example.com/item/1") == ""


def test_clean_spec_separator_and_spaces() -> None:
    assert clean_spec("20.5cmx6.0cm（小弯）----柯木汤勺批发") == "20.5cmx6.0cm（小弯）"
    assert clean_spec("----右侧规格") == "右侧规格"
    assert clean_spec("升级版白色250ml") == "升级版白色250ml"
    assert clean_spec("  A   B  ") == "A B"


def test_build_source_key_does_not_clean_product_master_values() -> None:
    assert build_source_key("https://example.com/item/1", "A   B----C") == ("https://example.com/item/1", "A   B----C")
