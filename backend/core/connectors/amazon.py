from datetime import timedelta

from django.utils import timezone

from .base import BaseConnector, ConnectorError


REGION_HOSTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}


class AmazonConnector(BaseConnector):
    capabilities = ["orders", "inventory", "shipments", "returns", "transactions", "settlements", "notifications", "backfill"]

    def __init__(self, account):
        super().__init__(account)
        self.base_url = self.settings.get("base_url") or REGION_HOSTS.get(account.region, REGION_HOSTS["NA"])
        self._access_token = None

    def access_token(self):
        if self._access_token:
            return self._access_token
        required = ["lwa_client_id", "lwa_client_secret", "refresh_token"]
        if any(not self.credentials.get(key) for key in required):
            raise ConnectorError("Amazon 缺少 LWA client id、client secret 或 refresh token")
        payload = self.request(
            "POST", "https://api.amazon.com/auth/o2/token", retries=2,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.credentials["refresh_token"],
                "client_id": self.credentials["lwa_client_id"],
                "client_secret": self.credentials["lwa_client_secret"],
            },
        )
        self._access_token = payload["access_token"]
        return self._access_token

    def headers(self):
        return {"x-amz-access-token": self.access_token(), "accept": "application/json", "content-type": "application/json"}

    def test_connection(self):
        return self.request("GET", f"{self.base_url}/sellers/v1/marketplaceParticipations", headers=self.headers())

    def pull_orders(self, cursor=None, since=None):
        path = self.settings.get("orders_path", "/orders/2026-01-01/orders")
        params = {"marketplaceIds": self.settings.get("marketplace_ids", self.credentials.get("marketplace_ids", []))}
        if cursor:
            params = {"nextToken": cursor}
        else:
            params["createdAfter"] = (since or timezone.now() - timedelta(days=2)).isoformat()
        payload = self.request("GET", f"{self.base_url}{path}", headers=self.headers(), params=params)
        body = payload.get("payload", payload)
        raw_orders = body.get("orders", body.get("Orders", []))
        for raw in raw_orders:
            if raw.get("items") or raw.get("Items"):
                continue
            order_id = raw.get("amazonOrderId") or raw.get("AmazonOrderId")
            if order_id:
                try:
                    item_payload = self.request("GET", f"{self.base_url}/orders/2026-01-01/orders/{order_id}/orderItems", headers=self.headers())
                    item_body = item_payload.get("payload", item_payload)
                    raw["items"] = [self._normalize_item(x) for x in item_body.get("orderItems", item_body.get("OrderItems", []))]
                except Exception:
                    raw["items"] = []
        orders = [self._normalize_order(item) for item in raw_orders]
        return orders, body.get("nextToken") or body.get("NextToken")

    def _normalize_order(self, raw):
        money = raw.get("orderTotal") or raw.get("OrderTotal") or {}
        return {
            "external_id": raw.get("amazonOrderId") or raw.get("AmazonOrderId"),
            "external_version": str(raw.get("lastUpdateDate") or raw.get("LastUpdateDate") or "1"),
            "marketplace": raw.get("marketplaceId") or raw.get("MarketplaceId") or "",
            "status": self._status(raw.get("orderStatus") or raw.get("OrderStatus")),
            "fulfillment": "fba" if (raw.get("fulfillmentChannel") or raw.get("FulfillmentChannel")) == "AFN" else "fbm",
            "ordered_at": raw.get("purchaseDate") or raw.get("PurchaseDate"),
            "buyer_name": "",
            "buyer_email": "",
            "ship_to": raw.get("shippingAddress") or {},
            "currency": money.get("currencyCode") or money.get("CurrencyCode") or "USD",
            "subtotal": money.get("amount") or money.get("Amount") or "0",
            "shipping_income": "0", "tax": "0", "discount": "0",
            "total": money.get("amount") or money.get("Amount") or "0",
            "items": raw.get("items", []),
            "raw": raw,
        }

    @staticmethod
    def _normalize_item(raw):
        price = raw.get("itemPrice") or raw.get("ItemPrice") or {}
        return {
            "external_line_id": raw.get("orderItemId") or raw.get("OrderItemId"),
            "external_sku": raw.get("sellerSku") or raw.get("SellerSKU"),
            "title": raw.get("title") or raw.get("Title", ""),
            "quantity": raw.get("quantityOrdered") or raw.get("QuantityOrdered", 1),
            "unit_price": price.get("amount") or price.get("Amount", 0),
            "tax": "0", "discount": "0",
        }

    @staticmethod
    def _status(value):
        return {"Pending": "pending", "Unshipped": "allocating", "PartiallyShipped": "partially_shipped", "Shipped": "shipped", "Canceled": "cancelled"}.get(value, "pending")

    def pull_inventory(self, cursor=None):
        params = {"granularityType": "Marketplace", "granularityId": self.settings.get("marketplace_ids", [""])[0], "details": "true"}
        if cursor:
            params["nextToken"] = cursor
        payload = self.request("GET", f"{self.base_url}/fba/inventory/v1/summaries", headers=self.headers(), params=params)
        body = payload.get("payload", {})
        rows = [{"external_sku": x.get("sellerSku"), "quantity": x.get("inventoryDetails", {}).get("fulfillableQuantity", 0), "node": "FBA"} for x in body.get("inventorySummaries", [])]
        return rows, body.get("nextToken")

    def push_inventory(self, items):
        seller_id = self.credentials.get("seller_id")
        marketplace_id = self.settings.get("marketplace_ids", [None])[0]
        errors = []
        for item in items:
            try:
                body = {"productType": self.settings.get("product_type", "PRODUCT"), "patches": [{"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": int(item["quantity"])}]}]}
                self.request("PATCH", f"{self.base_url}/listings/2021-08-01/items/{seller_id}/{item['external_sku']}", headers=self.headers(), params={"marketplaceIds": marketplace_id}, json=body)
            except Exception as exc:
                errors.append({"external_sku": item["external_sku"], "error": str(exc)})
        return {"accepted": len(items) - len(errors), "errors": errors}

    def push_tracking(self, shipment):
        order_id = shipment.order.external_id
        packages = list(shipment.packages.all())
        if not packages:
            raise ConnectorError("发货单没有包裹")
        package = packages[0]
        body = {
            "marketplaceId": shipment.order.store.marketplace,
            "packageDetail": {
                "packageReferenceId": shipment.shipment_no,
                "carrierCode": package.carrier,
                "trackingNumber": package.tracking_number,
                "shipDate": shipment.shipped_at.isoformat(),
                "orderItems": [{"orderItemId": str(x.order_item.external_line_id), "quantity": int(x.quantity)} for p in packages for x in p.items.all()],
            },
        }
        path = self.settings.get("confirm_shipment_path", f"/orders/v0/orders/{order_id}/shipmentConfirmation")
        return self.request("POST", f"{self.base_url}{path}", headers=self.headers(), json=body)

    def pull_transactions(self, cursor=None, since=None):
        params = {"postedAfter": (since or timezone.now() - timedelta(days=7)).isoformat()}
        if cursor:
            params = {"nextToken": cursor}
        payload = self.request("GET", f"{self.base_url}/finances/2024-06-19/transactions", headers=self.headers(), params=params)
        body = payload.get("payload", payload)
        return body.get("transactions", []), body.get("nextToken")
