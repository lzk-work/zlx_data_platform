"""Source URL validation and normalization."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..constants import (
    SOURCE_PLATFORM_1688,
    SOURCE_PLATFORM_OTHER,
    SOURCE_PLATFORM_TAOBAO,
    SOURCE_PLATFORM_TMALL,
)
from ..models.domain_models import CleanedSourceUrl

OFFER_ID_PATTERN = re.compile(r"/offer/(\d+)\.(?:html|htm)(?:$|[/?#&])", re.IGNORECASE)


def clean_source_url(raw_url: object) -> CleanedSourceUrl:
    """校验并清洗货源链接。

    Args:
        raw_url: 输入表中的货源链接原始值。

    Returns:
        CleanedSourceUrl: 清洗后的链接和识别出的货源平台。1688会归一到offer链接，
        淘宝和天猫第一版仅保留原链接。

    Raises:
        ValueError: 链接不是完整http/https地址，或1688链接无法识别offer ID时抛出。
    """
    text = str(raw_url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("货源链接必须是完整 http/https 链接")

    host = parsed.netloc.lower()
    path = parsed.path.strip()

    if "1688.com" in host:
        match = OFFER_ID_PATTERN.search(path)
        if not match:
            raise ValueError("1688 货源链接无法识别 offer ID")
        offer_id = match.group(1)
        return CleanedSourceUrl(
            source_url=f"https://detail.1688.com/offer/{offer_id}.html",
            source_platform=SOURCE_PLATFORM_1688,
        )

    if "taobao.com" in host:
        return CleanedSourceUrl(source_url=text, source_platform=SOURCE_PLATFORM_TAOBAO)

    if "tmall.com" in host or "tmall.hk" in host:
        return CleanedSourceUrl(source_url=text, source_platform=SOURCE_PLATFORM_TMALL)

    return CleanedSourceUrl(source_url=text, source_platform=SOURCE_PLATFORM_OTHER)
