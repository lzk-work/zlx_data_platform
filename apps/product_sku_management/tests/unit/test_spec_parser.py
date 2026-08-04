"""Spec parser tests."""

import pytest

from apps.product_sku_management.src.domain.spec_parser import parse_spec


def test_parse_spec_removes_quantity_from_identity_spec() -> None:
    (detail,) = parse_spec("白色||均码||3")

    assert detail.spec == "白色||均码"
    assert detail.display_spec_params == ("白色", "均码")
    assert detail.quantity == 3


def test_parse_spec_splits_only_when_whole_text_is_chinese_parenthesized_details() -> None:
    details = parse_spec("（白色||均码||1）（肤色||均码||2）")

    assert [detail.spec for detail in details] == ["白色||均码", "肤色||均码"]
    assert [detail.quantity for detail in details] == [1, 2]


def test_parse_spec_supports_mixed_outer_parentheses() -> None:
    details = parse_spec("（【S1款】水晶绒-点塑底40*60cm||1）（【S1款】水晶绒-点塑底40*120cm||1)")

    assert [detail.spec for detail in details] == [
        "【S1款】水晶绒-点塑底40*60cm",
        "【S1款】水晶绒-点塑底40*120cm",
    ]
    assert [detail.quantity for detail in details] == [1, 1]


def test_parse_spec_supports_inner_parentheses_inside_outer_groups() -> None:
    details = parse_spec("（白色||一公分散装（约24CM）||2）（黑色||一公分散装（约24CM）||2）（深肤（杏）||一公分散装（约24CM）||2）")

    assert [detail.spec for detail in details] == [
        "白色||一公分散装（约24CM）",
        "黑色||一公分散装（约24CM）",
        "深肤（杏）||一公分散装（约24CM）",
    ]
    assert [detail.quantity for detail in details] == [2, 2, 2]


def test_parse_spec_keeps_parentheses_inside_normal_spec_text() -> None:
    (detail,) = parse_spec("XL码（9-13岁）建议脚长20-25cm||5")

    assert detail.spec == "XL码（9-13岁）建议脚长20-25cm"
    assert detail.quantity == 5


def test_parse_spec_rejects_missing_quantity() -> None:
    with pytest.raises(ValueError, match="正整数数量"):
        parse_spec("白色||均码")


def test_parse_spec_rejects_missing_outer_open_parenthesis() -> None:
    with pytest.raises(ValueError, match="正整数数量"):
        parse_spec("(橙子||1)(芒果||1)青苹果||1)")
