import time
from abc import ABC, abstractmethod

import requests


class ConnectorError(RuntimeError):
    pass


class BaseConnector(ABC):
    capabilities = ["orders.read", "inventory.read", "tracking.push"]
    source_kind = "sales_channel"
    writable_actions = {"inventory.publish", "shipments.confirm", "tracking.push", "orders.acknowledge"}

    def __init__(self, account):
        self.account = account
        self.credentials = account.credentials
        self.settings = account.settings
        self.session = requests.Session()
        self.timeout = int(self.settings.get("timeout", 30))

    def request(self, method, url, *, retries=3, **kwargs):
        last_error = None
        for attempt in range(retries):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = int(response.headers.get("Retry-After", min(2 ** attempt, 8)))
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json() if response.content else {}
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(min(2 ** attempt, 8))
        raise ConnectorError(f"平台请求失败: {last_error}")

    @abstractmethod
    def test_connection(self): ...

    def discover_capabilities(self):
        return {
            "source_kind": self.source_kind,
            "capabilities": self.capabilities,
            "writable_actions": sorted(self.writable_actions),
        }

    def pull_changes(self, resource_type, cursor=None, since=None):
        handlers = {
            "orders": self.pull_order_changes,
            "returns": self.pull_returns,
            "inventory": lambda cursor=None, since=None: self.pull_inventory(cursor=cursor),
            "transactions": self.pull_transactions,
            "settlements": self.pull_settlements,
        }
        handler = handlers.get(resource_type)
        if not handler:
            raise ConnectorError(f"连接器不支持读取 {resource_type}")
        return handler(cursor=cursor, since=since)

    def fetch_object(self, resource_type, external_id):
        raise ConnectorError(f"连接器不支持单对象读取: {resource_type}")

    def normalize(self, resource_type, payload):
        return payload

    def validate(self, resource_type, payload):
        if not isinstance(payload, dict):
            raise ConnectorError("连接器记录必须是对象")
        return payload

    def push_action(self, action_type, payload):
        if action_type not in self.writable_actions:
            raise ConnectorError(f"写回动作不在白名单: {action_type}")
        if action_type == "inventory.publish":
            return self.push_inventory(payload.get("items", []))
        shipment = payload.get("shipment")
        if action_type in {"shipments.confirm", "tracking.push"} and shipment:
            return self.push_tracking(shipment)
        raise ConnectorError(f"写回动作缺少必要对象: {action_type}")

    def pull_orders(self, cursor=None, since=None):
        return [], None

    def pull_order_changes(self, cursor=None, since=None):
        return self.pull_orders(cursor=cursor, since=since)

    def pull_returns(self, cursor=None, since=None):
        return [], None

    def pull_inventory(self, cursor=None):
        return [], None

    def push_inventory(self, items):
        return {"accepted": len(items), "errors": []}

    def confirm_shipment(self, shipment):
        return self.push_tracking(shipment)

    def push_tracking(self, shipment):
        raise NotImplementedError

    def pull_transactions(self, cursor=None, since=None):
        return [], None

    def pull_settlements(self, cursor=None, since=None):
        return [], None

    def backfill(self, since, until=None):
        return self.pull_orders(since=since)

    def health(self):
        try:
            detail = self.test_connection()
            return {"ok": True, "provider": self.provider_key, "detail": detail}
        except Exception as exc:
            return {"ok": False, "provider": self.provider_key, "error": str(exc)}

    @property
    def provider_key(self):
        provider = getattr(self.account, "provider", "unknown")
        return getattr(provider, "key", provider)
