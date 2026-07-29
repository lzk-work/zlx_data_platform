"""飞书 OpenAPI 通用客户端。

这个模块只负责“怎么和飞书通信”，不负责具体业务字段含义。
后续产品开发、货源、图片、上架等应用都应该复用这里的能力，
不要在业务脚本里重复写获取 token、分页读取、回写记录等底层逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic, sleep
from typing import Any, Iterable

import httpx


class FeishuAPIError(RuntimeError):
    """飞书接口返回错误、HTTP 错误或网络重试失败时抛出。"""


@dataclass(frozen=True)
class FeishuConfig:
    """飞书客户端配置。

    app_id/app_secret 是飞书开放平台自建应用的凭证。
    tenant_access_token 不需要外部传入，由客户端自动获取和缓存。
    """

    app_id: str
    app_secret: str
    base_url: str = "https://open.feishu.cn"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.8


class FeishuClient:
    """飞书 OpenAPI 客户端。

    当前主要支持多维表格读取/回写和文本通知。
    这个类可以作为所有飞书相关应用的底层工具类。
    """

    def __init__(self, config: FeishuConfig) -> None:
        self.config = config
        self._tenant_access_token: str | None = None
        self._tenant_token_expires_at = 0.0
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def close(self) -> None:
        """关闭底层 HTTP 连接池。"""
        self._client.close()

    def __enter__(self) -> "FeishuClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def health_check(self) -> dict[str, Any]:
        """测试飞书应用凭证是否可用。

        这里只返回 token 前缀，避免完整 token 出现在日志或终端里。
        """
        token = self.tenant_access_token(force_refresh=True)
        return {"ok": True, "tenant_access_token_prefix": token[:8]}

    def tenant_access_token(self, force_refresh: bool = False) -> str:
        """获取并缓存 tenant_access_token。

        飞书的 token 有有效期。这里提前 5 分钟刷新，避免刚拿到 token
        去请求业务接口时已经接近过期。
        """
        if (
            not force_refresh
            and self._tenant_access_token
            and monotonic() < self._tenant_token_expires_at
        ):
            return self._tenant_access_token

        payload = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
        }
        data = self._request_json(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            json=payload,
            auth=False,
        )
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("Feishu token response did not include tenant_access_token")

        expire_seconds = int(data.get("expire", 7200))
        self._tenant_access_token = token
        self._tenant_token_expires_at = monotonic() + max(expire_seconds - 300, 60)
        return token


    def list_bitable_fields(
        self,
        app_token: str,
        table_id: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """分页读取多维表格字段结构，也就是表头/字段列表。

        这个方法用于检查飞书表结构，例如字段是否存在、字段类型是否符合预期。
        不要用记录数据反推表头，因为空字段可能不会在记录里体现。
        """
        fields: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token

            data = self._request_json(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                params=params,
            )
            fields.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break

        return fields
    def list_bitable_records(
        self,
        app_token: str,
        table_id: str,
        *,
        view_id: str | None = None,
        filter_expression: str | None = None,
        field_names: list[str] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """分页读取多维表格记录。

        app_token 是多维表格的 app_token，不是飞书应用 access token。
        这个方法会自动处理分页，调用方拿到的是完整记录列表。
        """
        records: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            if view_id:
                params["view_id"] = view_id
            if filter_expression:
                params["filter"] = filter_expression
            if field_names:
                params["field_names"] = field_names

            data = self._request_json(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            records.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break

        return records

    def get_bitable_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """按 record_id 读取一条多维表格记录。"""
        return self._request_json(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        ).get("record", {})

    def update_bitable_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """回写一条多维表格记录的字段。"""
        return self._request_json(
            "PUT",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            json={"fields": fields},
        )

    def create_bitable_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """新增一条多维表格记录。"""
        return self._request_json(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            json={"fields": fields},
        ).get("record", {})

    def batch_update_bitable_records(
        self,
        app_token: str,
        table_id: str,
        updates: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        """批量回写多维表格记录。

        每个 update item 需要包含 record_id 和 fields。
        空列表直接返回，避免调用飞书空请求。
        """
        records = list(updates)
        if not records:
            return {"records": []}
        return self._request_json(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
            json={"records": records},
        )

    def send_text_message(
        self,
        receive_id: str,
        text: str,
        *,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        """发送飞书文本消息。

        receive_id_type 常见值：chat_id、open_id、user_id、email。
        POC 阶段用于发送同步统计和异常数量提醒。
        """
        return self._request_json(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """统一发送飞书请求并解析 JSON 响应。

        这里集中处理鉴权头、HTTP 错误、飞书业务错误码和基础重试，
        让上层业务代码只关心“调用哪个能力”。
        """
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers["Authorization"] = f"Bearer {self.tenant_access_token()}"

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.request(method, path, headers=headers, **kwargs)
                response.raise_for_status()
                body = response.json()
                code = body.get("code", 0)
                if code != 0:
                    message = body.get("msg") or body.get("message") or "unknown error"
                    raise FeishuAPIError(f"Feishu API error code={code}: {message}")
                return body.get("data", body)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                sleep(self.config.retry_backoff_seconds * (attempt + 1))

        if isinstance(last_error, httpx.HTTPStatusError):
            response = last_error.response
            raise FeishuAPIError(f"Feishu HTTP error {response.status_code}: {response.text}") from last_error
        raise FeishuAPIError(f"Feishu request failed: {last_error}") from last_error
