from .amazon import AmazonConnector
from .mock import MockConnector
from .walmart import WalmartConnector
from .wayfair import WayfairConnector


CONNECTORS = {
    "amazon": AmazonConnector,
    "wayfair": WayfairConnector,
    "walmart": WalmartConnector,
    "mock": MockConnector,
}


def get_connector(account):
    connector_class = CONNECTORS.get(account.provider)
    if not connector_class:
        raise ValueError(f"未注册的连接器: {account.provider}")
    if account.settings.get("use_mock", account.environment == "sandbox" and not account.credentials):
        return MockConnector(account, simulated_provider=account.provider)
    return connector_class(account)

