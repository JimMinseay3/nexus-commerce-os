from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorRegistration:
    key: str
    connector_class: type


class ConnectorRegistry:
    def __init__(self):
        self._entries = {}

    def register(self, key, connector_class):
        self._entries[key] = ConnectorRegistration(key, connector_class)
        return connector_class

    def get(self, key):
        entry = self._entries.get(key)
        return entry.connector_class if entry else None

    def describe(self):
        return {
            key: {
                "source_kind": entry.connector_class.source_kind,
                "capabilities": entry.connector_class.capabilities,
                "writable_actions": sorted(entry.connector_class.writable_actions),
            }
            for key, entry in sorted(self._entries.items())
        }


registry = ConnectorRegistry()
