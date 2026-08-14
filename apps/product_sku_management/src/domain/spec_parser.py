"""Parse business source specs into product details."""

from __future__ import annotations

from dataclasses import dataclass

OPEN_PARENS = {"（", "("}
CLOSE_PARENS = {"）", ")"}
PAREN_PAIRS = {"（": {"）", ")"}, "(": {")", "）"}}


@dataclass(frozen=True)
class ParsedSpecDetail:
    """A single product detail parsed from a source spec."""

    raw_spec: str
    spec: str
    display_spec_params: tuple[str, ...]
    quantity: int


def parse_spec(raw_spec: object) -> tuple[ParsedSpecDetail, ...]:
    """解析货源规格单元格。

    Args:
        raw_spec: Excel中的规格原始值，支持单商品和中英文括号包裹的多商品格式。

    Returns:
        tuple[ParsedSpecDetail, ...]: 解析后的规格明细；spec字段不包含数量。

    Raises:
        ValueError: 规格为空、格式错误或数量不是正整数时抛出。
    """
    text = str(raw_spec or "").strip()
    if not text:
        raise ValueError("规格不能为空")

    chunks = split_outer_parenthesized_details(text) or [text]

    return tuple(_parse_one_detail(chunk) for chunk in chunks)


def split_outer_parenthesized_details(text: str) -> tuple[str, ...]:
    """按外层分组括号拆分多商品规格。

    Args:
        text: 原始规格文本。

    Returns:
        tuple[str, ...]: 完全由外层分组组成时返回明细内容；否则返回空元组。
    """
    chunks: list[str] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text):
            break
        if text[index] not in OPEN_PARENS:
            return ()

        close_index = find_outer_group_close(text, index + 1)
        if close_index is None:
            return ()

        chunk = text[index + 1:close_index].strip()
        if not chunk:
            return ()
        chunks.append(chunk)
        index = close_index + 1

    return tuple(chunks)


def find_outer_group_close(text: str, start_index: int) -> int | None:
    """查找当前外层分组的右括号。

    Args:
        text: 原始规格文本。
        start_index: 外层左括号后的起始位置。
    Returns:
        int | None: 外层右括号位置；找不到时返回None。
    """
    nested_close_stack: list[set[str]] = []
    for index in range(start_index, len(text)):
        char = text[index]
        if char in OPEN_PARENS:
            nested_close_stack.append(PAREN_PAIRS[char])
            continue

        if char not in CLOSE_PARENS:
            continue

        if nested_close_stack:
            if char in nested_close_stack[-1]:
                nested_close_stack.pop()
            continue

        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if next_index == len(text) or text[next_index] in OPEN_PARENS:
            return index
        return None
    return None


def _parse_one_detail(text: str) -> ParsedSpecDetail:
    """解析单个商品规格明细。

    Args:
        text: 单个商品的规格文本，格式为参数1||参数2||数量。

    Returns:
        ParsedSpecDetail: 包含原始规格、去数量规格、展示参数和数量。

    Raises:
        ValueError: 规格格式不合法时抛出。
    """
    parts = tuple(part.strip() for part in text.split("||"))
    if len(parts) < 2 or any(part == "" for part in parts):
        raise ValueError("规格必须使用 参数1||参数2||数量 格式")

    quantity_text = parts[-1]
    if not quantity_text.isdigit():
        raise ValueError("规格最后一个 || 后必须是正整数数量")

    quantity = int(quantity_text)
    if quantity <= 0:
        raise ValueError("规格数量必须大于 0")

    spec_params = parts[:-1]
    return ParsedSpecDetail(
        raw_spec=text,
        spec="||".join(spec_params),
        display_spec_params=spec_params,
        quantity=quantity,
    )
