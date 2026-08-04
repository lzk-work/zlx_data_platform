"""Logistics attribute mapping rules."""

from __future__ import annotations

DANGEROUS_TRANSPORT_CODE_BY_ATTRIBUTE = {
    "普货": "0",
    "带电": "1",
    "敏感": "2",
}


def dianxiaomi_dangerous_transport_code(logistics_attribute: str) -> str:
    """转换店小秘危险运输品编码。

    Args:
        logistics_attribute: 输入表中的产品属性，支持普货、带电、敏感。

    Returns:
        str: 店小秘危险运输品编码；空属性返回空字符串。

    Raises:
        ValueError: 属性不是普货、带电、敏感时抛出。
    """
    attribute = str(logistics_attribute or "").strip()
    if not attribute:
        return ""
    if attribute not in DANGEROUS_TRANSPORT_CODE_BY_ATTRIBUTE:
        raise ValueError("属性必须是 普货、带电、敏感 之一")
    return DANGEROUS_TRANSPORT_CODE_BY_ATTRIBUTE[attribute]
