"""字段标准化工具。"""

from __future__ import annotations

import re
from typing import Any


def normalize_text(value: Any) -> str:
    """把 Excel 单元格值标准化为去首尾空格的字符串。"""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def normalize_sku(value: Any) -> str:
    """标准化 SKU 文本。"""
    return normalize_text(value)


def clean_source_url(value: Any) -> str:
    """清洗货源链接，提取可稳定匹配的 1688/淘宝/天猫 URL。"""
    raw = normalize_text(value)
    if not raw:
        return ""

    normalized = raw
    if "1688" in normalized:
        offer_ids = _unique_in_order(re.findall(r"offer/(\d+)\.html", normalized))
        if not offer_ids:
            return ""
        urls = [f"https://detail.1688.com/offer/{offer_id}.html" for offer_id in offer_ids]
        if len(urls) == 1:
            return urls[0]
        return "\n".join(f"货源{index}:{url}" for index, url in enumerate(urls, start=1))

    if "taobao" in normalized:
        return _clean_item_url(normalized, "https://item.taobao.com/item.htm")

    if "tmall" in normalized:
        return _clean_item_url(normalized, "https://detail.tmall.com/item.htm")

    return ""


def clean_spec(value: Any) -> str:
    """清洗规格，统一空白并处理 3 到 5 个连续连字符分隔符。"""
    raw = normalize_text(value)
    if not raw:
        return ""

    compact = re.sub(r"\s+", " ", raw).strip()
    if not re.search(r"-{3,5}", compact):
        return compact

    normalized = re.sub(r"-{3,5}", "----", compact)
    delimiter_index = normalized.find("----")
    if delimiter_index == 0:
        cleaned = normalized[4:].strip()
    else:
        cleaned = normalized[:delimiter_index].strip()
    return cleaned or raw.strip()


def build_source_key(source_url: Any, spec: Any) -> tuple[str, str]:
    """构造货源匹配键。入参应已按来源完成清洗。"""
    return normalize_text(source_url), normalize_text(spec)


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _clean_item_url(raw: str, base_url: str) -> str:
    item_match = re.search(r"(?<![a-zA-Z_])id=(\d+)", raw)
    if not item_match:
        return ""
    result = f"{base_url}?id={item_match.group(1)}"
    sku_match = re.search(r"skuId=(\d+)", raw)
    if sku_match:
        result = f"{result}&skuId={sku_match.group(1)}"
    return result
