from datetime import timedelta

from django.utils import timezone

from .base import BaseConnector, ConnectorError


class WayfairConnector(BaseConnector):
    capabilities = ["orders.read", "returns.read", "inventory.read", "inventory.publish", "shipments.confirm", "tracking.push"]

    def __init__(self, account):
        super().__init__(account)
        default = "https://sandbox.api.wayfair.com/v1" if account.environment == "sandbox" else "https://api.wayfair.com/v1"
        self.base_url = self.settings.get("base_url", default)
        self._access_token = None

    def access_token(self):
        if self._access_token:
            return self._access_token
        client_id, client_secret = self.credentials.get("client_id"), self.credentials.get("client_secret")
        if not client_id or not client_secret:
            raise ConnectorError("Wayfair 缺少 client id 或 client secret")
        payload = self.request("POST", f"{self.base_url}/auth/token", retries=2, json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"})
        self._access_token = payload.get("access_token") or payload.get("token")
        if not self._access_token:
            raise ConnectorError("Wayfair 未返回 access token")
        return self._access_token

    def graphql(self, query, variables=None):
        payload = self.request("POST", f"{self.base_url}/graphql", headers={"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json"}, json={"query": query, "variables": variables or {}})
        if payload.get("errors"):
            raise ConnectorError(str(payload["errors"]))
        return payload.get("data", {})

    def test_connection(self):
        return self.graphql("query { __typename }")

    def pull_orders(self, cursor=None, since=None):
        query = self.settings.get("orders_query") or """
        query Orders($cursor: String, $since: DateTime!) {
          purchaseOrders(after: $cursor, updatedSince: $since) {
            nodes { poNumber status orderDate currency totalAmount supplierId shipTo { country state city postalCode } items { partNumber lineNumber quantity unitPrice } }
            pageInfo { endCursor hasNextPage }
          }
        }
        """
        data = self.graphql(query, {"cursor": cursor, "since": (since or timezone.now() - timedelta(days=2)).isoformat()})
        result = data.get("purchaseOrders", data.get("getDropshipPurchaseOrders", {}))
        rows = result.get("nodes", result.get("orders", []))
        orders = [self._normalize_order(row) for row in rows]
        page = result.get("pageInfo", {})
        return orders, page.get("endCursor") if page.get("hasNextPage") else None

    def _normalize_order(self, raw):
        items = [{"external_line_id": str(x.get("lineNumber", index + 1)), "external_sku": x.get("partNumber") or x.get("sku"), "title": x.get("name", ""), "quantity": str(x.get("quantity", 1)), "unit_price": str(x.get("unitPrice", 0)), "tax": "0", "discount": "0"} for index, x in enumerate(raw.get("items", []))]
        return {
            "external_id": str(raw.get("poNumber") or raw.get("purchaseOrderId")), "external_version": str(raw.get("updatedAt") or raw.get("orderDate") or "1"),
            "marketplace": self.account.settings.get("marketplace", "US"), "status": "pending", "fulfillment": "fbm",
            "ordered_at": raw.get("orderDate") or timezone.now().isoformat(), "buyer_name": "", "buyer_email": "",
            "ship_to": raw.get("shipTo", {}), "currency": raw.get("currency", "USD"), "subtotal": str(raw.get("totalAmount", 0)),
            "shipping_income": "0", "tax": "0", "discount": "0", "total": str(raw.get("totalAmount", 0)), "items": items, "raw": raw,
        }

    def push_inventory(self, items):
        mutation = self.settings.get("inventory_mutation") or "mutation SaveInventory($items: [InventoryInput!]!) { saveInventory(items: $items) { accepted errors { message } } }"
        data = self.graphql(mutation, {"items": [{"partNumber": x["external_sku"], "quantity": int(x["quantity"]), "warehouseId": x.get("node")} for x in items]})
        return data.get("saveInventory", {"accepted": len(items), "errors": []})

    def push_tracking(self, shipment):
        mutation = self.settings.get("shipment_mutation") or "mutation Ship($input: ShipmentInput!) { registerShipment(input: $input) { success message } }"
        packages = [{"carrier": p.carrier, "trackingNumber": p.tracking_number, "shipDate": shipment.shipped_at.isoformat(), "items": [{"lineNumber": x.order_item.external_line_id, "quantity": float(x.quantity)} for x in p.items.all()]} for p in shipment.packages.all()]
        return self.graphql(mutation, {"input": {"poNumber": shipment.order.external_id, "packages": packages}})
