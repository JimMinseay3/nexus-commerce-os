from .base import BaseConnector, ConnectorError


class FileConnector(BaseConnector):
    source_kind = "file"
    capabilities = ["catalog.read", "orders.read", "inventory.read", "procurement.read", "finance.read"]
    writable_actions = set()

    def test_connection(self):
        return {"ok": True, "mode": "mapping-upload", "message": "Excel/CSV 通过统一映射中心导入"}

    def pull_changes(self, resource_type, cursor=None, since=None):
        return [], None

    def push_action(self, action_type, payload):
        raise ConnectorError("文件连接器不支持外部写回")
