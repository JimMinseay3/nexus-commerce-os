from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .base import BaseConnector


class MockConnector(BaseConnector):
    capabilities = ["catalog.read", "orders.read", "returns.read", "inventory.read", "inventory.publish", "shipments.confirm", "tracking.push", "finance.read", "settlements.read"]

    def __init__(self, account, simulated_provider=None):
        super().__init__(account)
        self.simulated_provider = simulated_provider or account.provider

    def test_connection(self):
        return {"mode": "local-simulator", "provider": self.simulated_provider, "account": self.account.name}

    def pull_orders(self, cursor=None, since=None):
        sequence = int(cursor or 0)
        if sequence > 0:
            return [], str(sequence)
        ordered_at = timezone.now() - timedelta(hours=2)
        prefix = self.simulated_provider.upper()[:3]
        order = {
            "external_id": f"{prefix}-DEMO-10001",
            "external_version": "1",
            "marketplace": self.settings.get("marketplace", "US"),
            "status": "pending",
            "fulfillment": self.settings.get("fulfillment", "fbm"),
            "ordered_at": ordered_at.isoformat(),
            "buyer_name": "模拟客户",
            "buyer_email": "masked@example.invalid",
            "ship_to": {"country": "US", "state": "CA", "city": "Los Angeles", "postal_code": "90001"},
            "currency": "USD",
            "subtotal": "399.00",
            "shipping_income": "39.00",
            "tax": "0",
            "discount": "10.00",
            "total": "428.00",
            "items": [{
                "external_line_id": "1",
                "external_sku": self.settings.get("demo_sku", "CHAIR-OAK-001"),
                "title": "北欧橡木餐椅",
                "quantity": "1",
                "unit_price": "399.00",
                "tax": "0",
                "discount": "10.00",
            }],
            "raw": {"simulated": True, "provider": self.simulated_provider},
        }
        return [order], "1"

    def pull_inventory(self, cursor=None):
        return [{"external_sku": self.settings.get("demo_sku", "CHAIR-OAK-001"), "quantity": Decimal("18"), "node": "MOCK-FC"}], "1"

    def push_inventory(self, items):
        return {"accepted": len(items), "errors": [], "simulated": True}

    def push_tracking(self, shipment):
        return {"accepted": True, "shipment_no": shipment.shipment_no, "simulated": True}

    def pull_returns(self, cursor=None, since=None):
        return [], cursor

    def pull_transactions(self, cursor=None, since=None):
        return [], cursor

    def pull_settlements(self, cursor=None, since=None):
        return [], cursor
