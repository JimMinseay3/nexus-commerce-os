from datetime import timedelta

from django.utils import timezone

from core.connectors import get_connector
from core.models import OutboundAction, Shipment


WRITE_WHITELIST = {"inventory.publish", "shipments.confirm", "tracking.push", "orders.acknowledge"}


def queue_action(connection, action_type, payload, idempotency_key, canonical_entity_type="", canonical_entity_id=None):
    if action_type not in WRITE_WHITELIST:
        raise ValueError(f"写回动作不在 NEXUS 白名单: {action_type}")
    if action_type not in connection.provider.capabilities:
        raise ValueError(f"{connection.provider.name} 未声明写回能力 {action_type}")
    action, _ = OutboundAction.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"connection": connection, "action_type": action_type, "payload": payload,
                  "canonical_entity_type": canonical_entity_type, "canonical_entity_id": canonical_entity_id},
    )
    return action


def execute_action(action):
    if action.status == "succeeded":
        return action.result
    payload = dict(action.payload)
    if action.action_type in {"shipments.confirm", "tracking.push"}:
        shipment_id = payload.pop("shipment_id", None) or action.canonical_entity_id
        payload["shipment"] = Shipment.objects.get(pk=shipment_id)
    action.status, action.attempts = "running", action.attempts + 1
    action.save(update_fields=["status", "attempts", "updated_at"])
    try:
        result = get_connector(action.connection).push_action(action.action_type, payload)
        action.status, action.result, action.error, action.next_retry_at = "succeeded", result or {}, "", None
        return action.result
    except Exception as exc:
        action.status, action.error = "failed", str(exc)
        action.next_retry_at = timezone.now() + timedelta(minutes=min(2 ** action.attempts, 60))
        raise
    finally:
        action.save(update_fields=["status", "result", "error", "next_retry_at", "updated_at"])
