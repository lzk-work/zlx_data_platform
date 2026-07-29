"""POC 专用飞书客户端封装。

底层能力来自 connectors.feishu.FeishuClient。
这里的作用只是把 POC 配置转换成通用客户端需要的配置对象。
"""

from __future__ import annotations

from connectors.feishu import FeishuClient as BaseFeishuClient
from connectors.feishu import FeishuConfig

from .settings import IntakeSettings


class FeishuClient(BaseFeishuClient):
    """从 POC settings 创建的飞书客户端。"""

    @classmethod
    def from_settings(cls, settings: IntakeSettings) -> "FeishuClient":
        """用 .env 中的飞书应用凭证创建客户端。"""
        return cls(FeishuConfig(settings.feishu_app_id, settings.feishu_app_secret))
