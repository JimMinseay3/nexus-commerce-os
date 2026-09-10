from .amazon import AmazonConnector
from .ebay import EbayConnector
from .file import FileConnector
from .lingxing import LingxingConnector
from .mock import MockConnector
from .walmart import WalmartConnector
from .wayfair import WayfairConnector
from .registry import registry


for key, connector_class in {
    "amazon": AmazonConnector, "ebay": EbayConnector, "wayfair": WayfairConnector,
    "walmart": WalmartConnector, "lingxing": LingxingConnector, "file": FileConnector, "mock": MockConnector,
}.items():
    registry.register(key, connector_class)

CONNECTORS = {key: entry.connector_class for key, entry in registry._entries.items()}


def get_connector(account):
    provider = getattr(account, "provider", "")
    provider_key = getattr(provider, "key", provider)
    connector_class = registry.get(provider_key)
    if not connector_class:
        raise ValueError(f"未注册的连接器: {provider_key}")
    if account.settings.get("use_mock", account.environment == "sandbox" and not account.credentials):
        return MockConnector(account, simulated_provider=provider_key)
    return connector_class(account)


def describe_connectors():
    return registry.describe()
