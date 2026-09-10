from .base import BaseConnector, ConnectorError


class LingxingConnector(BaseConnector):
    source_kind = "erp"
    capabilities = ["catalog.read", "orders.read", "inventory.read", "procurement.read", "finance.read", "settlements.read"]
    writable_actions = set()

    def __init__(self, account):
        super().__init__(account)
        self.base_url = self.settings.get("base_url", "https://openapi.lingxing.com")
        self._access_token = None

    def access_token(self):
        if self._access_token:
            return self._access_token
        app_id, app_secret = self.credentials.get("app_id"), self.credentials.get("app_secret")
        if not app_id or not app_secret:
            raise ConnectorError("领星缺少 AppID 或 AppSecret")
        token_path = self.settings.get("token_path")
        if not token_path:
            raise ConnectorError("请根据领星开放后台配置 token_path")
        payload = self.request("POST", f"{self.base_url}{token_path}", retries=2, json={"appId": app_id, "appSecret": app_secret})
        self._access_token = payload.get("data", {}).get("access_token") or payload.get("access_token")
        if not self._access_token:
            raise ConnectorError("领星未返回 access token")
        return self._access_token

    def headers(self):
        return {"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json"}

    def _configured_path(self, key):
        path = self.settings.get("paths", {}).get(key)
        if not path:
            raise ConnectorError(f"请根据领星账号权限配置 {key} 接口路径")
        return path

    def test_connection(self):
        return self.request("GET", f"{self.base_url}{self._configured_path('accounts')}", headers=self.headers())

    def pull_changes(self, resource_type, cursor=None, since=None):
        path = self._configured_path(resource_type)
        offset = int(cursor or 0)
        payload = self.request("POST", f"{self.base_url}{path}", headers=self.headers(), json={"offset": offset, "limit": 100, "start_time": since.isoformat() if since else None})
        body = payload.get("data", payload)
        rows = body.get("list", body.get("items", [])) if isinstance(body, dict) else []
        next_cursor = str(offset + len(rows)) if len(rows) == 100 else None
        if resource_type == "orders":
            rows = [self._normalize_order(row) for row in rows]
        return rows, next_cursor

    def pull_orders(self, cursor=None, since=None):
        return self.pull_changes("orders", cursor=cursor, since=since)

    def _normalize_order(self, raw):
        items = raw.get("items") or raw.get("order_items") or []
        return {
            "external_id": str(raw.get("amazon_order_id") or raw.get("channel_order_id") or raw.get("order_id")),
            "external_version": str(raw.get("updated_at") or raw.get("update_time") or "1"),
            "marketplace": str(raw.get("marketplace_id") or raw.get("marketplace") or ""),
            "status": "pending", "source_status": str(raw.get("status", "")), "source_timezone": self.settings.get("source_timezone", "Asia/Shanghai"),
            "fulfillment": str(raw.get("fulfillment", "fbm")).lower(), "ordered_at": raw.get("order_time") or raw.get("purchase_date"),
            "buyer_name": "", "buyer_email": "", "ship_to": raw.get("ship_to", {}),
            "currency": raw.get("currency", "USD"), "subtotal": raw.get("subtotal", raw.get("total", 0)),
            "shipping_income": raw.get("shipping", 0), "tax": raw.get("tax", 0), "discount": raw.get("discount", 0), "total": raw.get("total", 0),
            "items": [{"external_line_id": str(item.get("line_id") or index + 1), "external_sku": item.get("sku") or item.get("seller_sku", ""), "title": item.get("title", ""), "quantity": item.get("quantity", 1), "unit_price": item.get("unit_price", 0), "tax": item.get("tax", 0), "discount": item.get("discount", 0)} for index, item in enumerate(items)],
            "extensions": {"lingxing": {"sid": raw.get("sid"), "internal_order_id": raw.get("order_id")}}, "raw": raw,
        }

    def push_action(self, action_type, payload):
        raise ConnectorError("领星连接器第一期仅允许读取和对账")
