import base64
import uuid
from datetime import timedelta

from django.utils import timezone

from .base import BaseConnector, ConnectorError


class WalmartConnector(BaseConnector):
    capabilities = ["orders", "inventory", "shipments", "returns", "transactions", "settlements", "backfill"]

    def __init__(self, account):
        super().__init__(account)
        self.base_url = self.settings.get("base_url") or ("https://sandbox.walmartapis.com" if account.environment == "sandbox" else "https://marketplace.walmartapis.com")
        self._access_token = None

    def access_token(self):
        if self._access_token:
            return self._access_token
        client_id, client_secret = self.credentials.get("client_id"), self.credentials.get("client_secret")
        if not client_id or not client_secret:
            raise ConnectorError("Walmart 缺少 client id 或 client secret")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        payload = self.request("POST", f"{self.base_url}/v3/token", retries=2, headers={"Authorization": f"Basic {basic}", "WM_QOS.CORRELATION_ID": str(uuid.uuid4()), "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, data={"grant_type": "client_credentials"})
        self._access_token = payload["access_token"]
        return self._access_token

    def headers(self):
        return {"WM_SEC.ACCESS_TOKEN": self.access_token(), "WM_QOS.CORRELATION_ID": str(uuid.uuid4()), "WM_SVC.NAME": "ERP", "Accept": "application/json", "Content-Type": "application/json"}

    def test_connection(self):
        return self.request("GET", f"{self.base_url}/v3/orders", headers=self.headers(), params={"limit": 1})

    def pull_orders(self, cursor=None, since=None):
        params = {"limit": 100, "createdStartDate": (since or timezone.now() - timedelta(days=2)).isoformat()}
        if cursor:
            params["nextCursor"] = cursor
        payload = self.request("GET", f"{self.base_url}/v3/orders", headers=self.headers(), params=params)
        order_list = payload.get("list", payload).get("elements", {}).get("order", [])
        orders = [self._normalize_order(x) for x in order_list]
        meta = payload.get("list", payload).get("meta", {})
        return orders, meta.get("nextCursor")

    def _normalize_order(self, raw):
        lines = raw.get("orderLines", {}).get("orderLine", [])
        items, subtotal = [], 0
        for line in lines:
            price = line.get("charges", {}).get("charge", [{}])[0].get("chargeAmount", {}).get("amount", 0)
            qty = line.get("orderLineQuantity", {}).get("amount", 1)
            subtotal += float(price) * float(qty)
            items.append({"external_line_id": str(line.get("lineNumber")), "external_sku": line.get("item", {}).get("sku"), "title": line.get("item", {}).get("productName", ""), "quantity": str(qty), "unit_price": str(price), "tax": "0", "discount": "0"})
        status = (lines[0].get("orderLineStatuses", {}).get("orderLineStatus", [{}])[0].get("status") if lines else "Created")
        return {
            "external_id": raw.get("purchaseOrderId"), "external_version": str(raw.get("orderDate", "1")),
            "marketplace": self.account.settings.get("marketplace", "US"),
            "status": {"Created": "pending", "Acknowledged": "allocating", "Shipped": "shipped", "Cancelled": "cancelled"}.get(status, "pending"),
            "fulfillment": "wfs" if raw.get("fulfillmentOption") == "DELIVERY" and self.account.settings.get("wfs") else "fbm",
            "ordered_at": raw.get("orderDate"), "buyer_name": "", "buyer_email": "",
            "ship_to": raw.get("shippingInfo", {}).get("postalAddress", {}), "currency": "USD",
            "subtotal": str(subtotal), "shipping_income": "0", "tax": "0", "discount": "0", "total": str(subtotal),
            "items": items, "raw": raw,
        }

    def pull_inventory(self, cursor=None):
        payload = self.request("GET", f"{self.base_url}/v3/inventories", headers=self.headers())
        rows = [{"external_sku": x.get("sku"), "quantity": x.get("quantity", {}).get("amount", 0), "node": x.get("shipNode", "DEFAULT")} for x in payload.get("elements", {}).get("inventories", [])]
        return rows, None

    def push_inventory(self, items):
        errors = []
        for item in items:
            body = {"sku": item["external_sku"], "quantity": {"unit": "EACH", "amount": int(item["quantity"])}}
            try:
                self.request("PUT", f"{self.base_url}/v3/inventory", headers=self.headers(), json=body)
            except Exception as exc:
                errors.append({"external_sku": item["external_sku"], "error": str(exc)})
        return {"accepted": len(items) - len(errors), "errors": errors}

    def push_tracking(self, shipment):
        lines = []
        for package in shipment.packages.all():
            for item in package.items.all():
                lines.append({"lineNumber": item.order_item.external_line_id, "orderLineStatuses": {"orderLineStatus": [{"status": "Shipped", "statusQuantity": {"unitOfMeasurement": "EACH", "amount": str(item.quantity)}, "trackingInfo": {"shipDateTime": shipment.shipped_at.isoformat(), "carrierName": {"carrier": package.carrier}, "methodCode": package.service or "Standard", "trackingNumber": package.tracking_number}}]}})
        return self.request("POST", f"{self.base_url}/v3/orders/{shipment.order.external_id}/shipping", headers=self.headers(), json={"orderShipment": {"orderLines": {"orderLine": lines}}})

    def pull_returns(self, cursor=None, since=None):
        payload = self.request("GET", f"{self.base_url}/v3/returns", headers=self.headers(), params={"returnOrderId": cursor} if cursor else {})
        return payload.get("returnOrders", []), None

