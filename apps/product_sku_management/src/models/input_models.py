"""Input models for platform listing supplement workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SourceGroupInput:
    """One numbered source group from the business input sheet."""

    group_no: int
    source_url: str
    spec: str
    note: str = ""
    purchase_price_rmb: Decimal | None = None
    weight_kg: Decimal | None = None


@dataclass(frozen=True)
class PlatformListingInputRow:
    """A row where one platform SKU represents one sales unit."""

    row_no: int
    shop_name: str
    platform_sku: str
    first_level_category: str
    main_image_url: str = ""
    length_cm: Decimal | None = None
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    logistics_attribute: str = ""
    chinese_customs_name: str = ""
    development_note: str = ""
    source_groups: tuple[SourceGroupInput, ...] = field(default_factory=tuple)
    raw_row: dict[str, Any] = field(default_factory=dict)

