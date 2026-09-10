import time
from abc import ABC, abstractmethod

import requests


class ConnectorError(RuntimeError):
    pass


class BaseConnector(ABC):
    capabilities = ["orders", "inventory", "shipments"]

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
        return self.capabilities

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
            return {"ok": True, "provider": self.account.provider, "detail": detail}
        except Exception as exc:
            return {"ok": False, "provider": self.account.provider, "error": str(exc)}

