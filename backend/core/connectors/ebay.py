import base64
from datetime import timedelta

from django.utils import timezone

from .base import BaseConnector, ConnectorError


class EbayConnector(BaseConnector):
    source_kind = "sales_channel"
    capabilities = ["orders.read", "returns.read", "inventory.read", "finance.read", "inventory.publish", "tracking.push"]
    writable_actions = {"inventory.publish", "tracking.push", "shipments.confirm"}

    def __init__(self, account):
        super().__init__(account)
        sandbox = getattr(account, "environment", "sandbox") == "sandbox"
        self.base_url = self.settings.get("base_url") or ("https://api.sandbox.ebay.com" if sandbox else "https://api.ebay.com")
        self.finances_base_url = self.settings.get("finances_base_url") or ("https://apiz.sandbox.ebay.com" if sandbox else "https://apiz.ebay.com")
        self._access_token = None

    def access_token(self):
        if self._access_token:
            return self._access_token
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        refresh_token = self.credentials.get("refresh_token")
        if not all([client_id, client_secret, refresh_token]):
            raise ConnectorError("eBay 缺少 client id、client secret 或 refresh token")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        payload = self.request(
            "POST", f"{self.base_url}/identity/v1/oauth2/token", retries=2,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token, "scope": self.settings.get("oauth_scope", "https://api.ebay.com/oauth/api_scope/sell.fulfillment https://api.ebay.com/oauth/api_scope/sell.inventory")},
        )
        self._access_token = payload["access_token"]
        return self._access_token

    def headers(self):
        return {"Authorization": f"Bearer {self.access_token()}", "Accept": "application/json", "Content-Type": "application/json"}

    def test_connection(self):
        return self.request("GET", f"{self.base_url}/sell/fulfillment/v1/order", headers=self.headers(), params={"limit": 1})

    def pull_orders(self, cursor=None, since=None):
        offset = int(cursor or 0)
        oldest_supported = timezone.now() - timedelta(days=90)
        since = max(since or timezone.now() - timedelta(days=2), oldest_supported)
        params = {"limit": 100, "offset": offset, "filter": f"lastmodifieddate:[{since:%Y-%m-%dT%H:%M:%S.000Z}..]"}
        payload = self.request("GET", f"{self.base_url}/sell/fulfillment/v1/order", headers=self.headers(), params=params)
        rows = [self._normalize_order(row) for row in payload.get("orders", [])]
        total = int(payload.get("total", len(rows)))
        next_cursor = str(offset + len(rows)) if offset + len(rows) < total else None
        return rows, next_cursor

    def _normalize_order(self, raw):
        pricing = raw.get("pricingSummary", {})
        total = pricing.get("total", {})
        ship_to = raw.get("fulfillmentStartInstructions", [{}])[0].get("shippingStep", {}).get("shipTo", {})
        items = []
        for line in raw.get("lineItems", []):
            price = line.get("lineItemCost", {})
            items.append({
                "external_line_id": line.get("lineItemId"), "external_sku": line.get("sku", ""),
                "title": line.get("title", ""), "quantity": line.get("quantity", 1),
                "unit_price": price.get("value", 0), "tax": "0", "discount": "0",
                "extensions": {"ebay": {"legacy_item_id": line.get("legacyItemId")}},
            })
        return {
            "external_id": raw.get("orderId"), "external_version": str(raw.get("lastModifiedDate") or "1"),
            "marketplace": raw.get("salesRecordReference", self.settings.get("marketplace", "EBAY_US")),
            "status": {"NOT_STARTED": "pending", "IN_PROGRESS": "partially_shipped", "FULFILLED": "shipped"}.get(raw.get("orderFulfillmentStatus"), "pending"),
            "source_status": raw.get("orderFulfillmentStatus", ""), "source_timezone": "UTC", "fulfillment": "fbm",
            "ordered_at": raw.get("creationDate"), "buyer_name": "", "buyer_email": "", "ship_to": ship_to,
            "currency": total.get("currency", "USD"), "subtotal": pricing.get("priceSubtotal", {}).get("value", total.get("value", 0)),
            "shipping_income": pricing.get("deliveryCost", {}).get("value", 0), "tax": pricing.get("tax", {}).get("value", 0),
            "discount": pricing.get("totalSavings", {}).get("value", 0), "total": total.get("value", 0),
            "items": items, "extensions": {"ebay": {"buyer_username": raw.get("buyer", {}).get("username")}}, "raw": raw,
        }

    def push_inventory(self, items):
        requests = [{"sku": item["external_sku"], "shipToLocationAvailability": {"quantity": int(item["quantity"])}} for item in items]
        return self.request("POST", f"{self.base_url}/sell/inventory/v1/bulk_update_price_quantity", headers=self.headers(), json={"requests": requests})

    def pull_inventory(self, cursor=None):
        offset = int(cursor or 0)
        payload = self.request("GET", f"{self.base_url}/sell/inventory/v1/inventory_item", headers=self.headers(), params={"limit": 100, "offset": offset})
        items = payload.get("inventoryItems", [])
        rows = [{"external_sku": item.get("sku"), "quantity": item.get("availability", {}).get("shipToLocationAvailability", {}).get("quantity", 0), "node": self.settings.get("inventory_node", "EBAY") , "raw": item} for item in items]
        total = int(payload.get("total", len(items)))
        return rows, str(offset + len(items)) if offset + len(items) < total else None

    def pull_returns(self, cursor=None, since=None):
        offset = int(cursor or 0)
        path = self.settings.get("returns_path", "/post-order/v2/return/search")
        params = {"limit": 100, "offset": offset}
        if since:
            params["creation_date_range_from"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload = self.request("GET", f"{self.base_url}{path}", headers=self.headers(), params=params)
        raw_rows = payload.get("members", payload.get("returns", []))
        rows = [{
            "return_id": (row.get("summary") or row).get("returnId") or row.get("returnRequestId") or row.get("id"),
            "order_id": (row.get("summary") or row).get("orderId") or row.get("legacyOrderId"),
            "status": (row.get("summary") or row).get("status", "requested"), "reason": (row.get("summary") or row).get("returnReason", ""),
            "refundAmount": ((row.get("summary") or row).get("sellerTotalRefund") or {}).get("actualRefundAmount", {}).get("value", 0),
            "items": row.get("items", []), "raw": row,
        } for row in raw_rows]
        total = int(payload.get("paginationOutput", {}).get("totalEntries", payload.get("total", len(rows))))
        return rows, str(offset + len(rows)) if offset + len(rows) < total else None

    def pull_transactions(self, cursor=None, since=None):
        offset = int(cursor or 0)
        since = since or timezone.now() - timedelta(days=7)
        payload = self.request("GET", f"{self.finances_base_url}/sell/finances/v1/transaction", headers=self.headers(), params={"limit": 100, "offset": offset, "filter": f"transactionDate:[{since:%Y-%m-%dT%H:%M:%S.000Z}..]"})
        rows = payload.get("transactions", [])
        total = int(payload.get("total", len(rows)))
        return rows, str(offset + len(rows)) if offset + len(rows) < total else None

    def push_tracking(self, shipment):
        packages = list(shipment.packages.all())
        body = {
            "lineItems": [{"lineItemId": item.order_item.external_line_id, "quantity": int(item.quantity)} for package in packages for item in package.items.all()],
            "shippedDate": shipment.shipped_at.isoformat(),
            "shippingCarrierCode": packages[0].carrier if packages else "OTHER",
            "trackingNumber": packages[0].tracking_number if packages else "",
        }
        return self.request("POST", f"{self.base_url}/sell/fulfillment/v1/order/{shipment.order.external_id}/shipping_fulfillment", headers=self.headers(), json=body)
