import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.connectors import get_connector
from core.models import (
    DataConflict, ExternalIdentity, IngestionRun, IntegrationConnection, Order,
    OutboxEvent, RawRecord,
)
from .mapping import apply_mapping
from .sync import _reconcile_external_inventory, _upsert_finance_entry, _upsert_return, upsert_normalized_order


def payload_digest(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def order_fingerprint(data):
    ordered = str(data.get("ordered_at", ""))[:16]
    skus = sorted(str(item.get("external_sku", "")) for item in data.get("items", []))
    raw = "|".join([ordered, str(data.get("currency", "")), str(data.get("total", "")), ",".join(skus)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _provider_key(connection):
    return connection.provider.key


def _attach_identity(connection, object_type, external_id, scope, canonical_type, canonical_id, method="exact", confidence=1):
    identity, _ = ExternalIdentity.objects.update_or_create(
        company=connection.company, connection=connection, object_type=object_type,
        external_id=str(external_id), scope=scope or "",
        defaults={"canonical_entity_type": canonical_type, "canonical_entity_id": canonical_id, "resolution_method": method, "confidence": confidence},
    )
    return identity


def _candidate_order(company, data):
    ordered_at = data.get("ordered_at")
    if isinstance(ordered_at, str):
        ordered_at = parse_datetime(ordered_at)
    queryset = Order.objects.filter(company=company, currency=data.get("currency", "USD"), total=Decimal(str(data.get("total", 0))))
    if ordered_at:
        queryset = queryset.filter(ordered_at__gte=ordered_at - timedelta(minutes=5), ordered_at__lte=ordered_at + timedelta(minutes=5))
    return queryset.first()


def _canonical_order_payload(mapped):
    """Translate governed order.* fields to the domain service contract."""
    order = mapped.get("order", mapped)
    money = order.get("total", {})
    total = money.get("amount", 0) if isinstance(money, dict) else money
    currency = money.get("currency") if isinstance(money, dict) else None
    return {
        "external_id": order.get("channel_order_id") or order.get("external_id"),
        "external_version": order.get("external_version", "1"),
        "marketplace": order.get("marketplace", ""), "status": order.get("status", "pending"),
        "source_status": order.get("source_status", ""), "source_timezone": order.get("source_timezone", "UTC"),
        "fulfillment": order.get("fulfillment", "fbm"), "ordered_at": order.get("ordered_at"),
        "buyer_name": order.get("buyer_name", ""), "buyer_email": order.get("buyer_email", ""),
        "ship_to": order.get("ship_to", {}), "currency": order.get("currency") or currency or "USD",
        "subtotal": order.get("subtotal", total), "shipping_income": order.get("shipping_income", 0),
        "tax": order.get("tax", 0), "discount": order.get("discount", 0), "total": total,
        "items": order.get("items", []), "extensions": order.get("extensions", {}), "raw": mapped,
    }


def _merge_order(connection, data, raw_record):
    external_id = str(data["external_id"])
    scope = str(data.get("marketplace", ""))
    source_kind = connection.provider.source_kind
    identity_query = ExternalIdentity.objects.filter(
        company=connection.company, object_type="order", external_id=external_id,
        canonical_entity_type="order",
    )
    if scope:
        identity_query = identity_query.filter(scope=scope)
    if source_kind == "sales_channel":
        identity_query = identity_query.filter(connection__provider=connection.provider)
    existing_identity = identity_query.first()
    existing = Order.objects.filter(company=connection.company, pk=existing_identity.canonical_entity_id).first() if existing_identity else None
    if not existing:
        direct = Order.objects.filter(company=connection.company, external_id=external_id)
        if scope:
            direct = direct.filter(store__marketplace=scope)
        if source_kind == "sales_channel":
            direct = direct.filter(store__account__provider=connection.provider.key)
        existing = direct.first()
    if existing:
        extensions = existing.extensions.copy()
        extensions[_provider_key(connection)] = data.get("extensions", {}).get(_provider_key(connection), data.get("extensions", {}))
        existing.extensions = extensions
        if source_kind == "sales_channel":
            existing.external_version = data.get("external_version", existing.external_version)
            existing.source_status = data.get("source_status", existing.source_status)
            existing.source_timezone = data.get("source_timezone", existing.source_timezone)
            for field in ["currency", "subtotal", "shipping_income", "tax", "discount", "total"]:
                if field in data:
                    setattr(existing, field, data[field])
            existing.raw_payload = data.get("raw", data)
            existing.save(update_fields=["external_version", "extensions", "source_status", "source_timezone", "currency", "subtotal", "shipping_income", "tax", "discount", "total", "raw_payload", "updated_at"])
        else:
            for field in ["currency", "total"]:
                current, incoming = getattr(existing, field), data.get(field)
                different = (Decimal(str(current)) != Decimal(str(incoming))) if field == "total" and incoming not in (None, "") else str(current) != str(incoming)
                if incoming not in (None, "") and different:
                    if not DataConflict.objects.filter(company=connection.company, canonical_entity_id=existing.id, field_key=f"order.{field}", incoming_source=connection.name, status="open").exists():
                        DataConflict.objects.create(
                            company=connection.company, object_type="order", canonical_entity_type="order",
                            canonical_entity_id=existing.id, field_key=f"order.{field}", current_value=str(current),
                            incoming_value=str(incoming), current_source="sales_channel", incoming_source=connection.name,
                            reason="参考系统值与渠道权威事实不一致，未覆盖 NEXUS 订单",
                        )
            existing.save(update_fields=["extensions", "updated_at"])
        order = existing
        method = "channel_order_id"
    else:
        candidate = _candidate_order(connection.company, data)
        if candidate:
            DataConflict.objects.get_or_create(
                company=connection.company, object_type="order", canonical_entity_type="order",
                canonical_entity_id=candidate.id, field_key="order.identity",
                incoming_source=connection.name, current_source=candidate.store.name,
                reason="订单指纹相似但缺少可靠渠道订单号，禁止自动合并",
                defaults={"current_value": {"external_id": candidate.external_id}, "incoming_value": {"external_id": external_id, "fingerprint": order_fingerprint(data)}},
            )
        if not connection.legacy_account:
            raw_record.status = "quarantined"
            raw_record.error = "连接尚未关联兼容渠道账号，标准订单暂不落库"
            raw_record.save(update_fields=["status", "error", "updated_at"])
            return None
        order = upsert_normalized_order(connection.legacy_account, data)
        order.source_status = data.get("source_status", "")
        order.source_timezone = data.get("source_timezone", "UTC")
        order.extensions = data.get("extensions", {})
        order.save(update_fields=["source_status", "source_timezone", "extensions", "updated_at"])
        method = "created"
    _attach_identity(connection, "order", external_id, scope, "order", order.id, method)
    raw_record.status = "merged"
    raw_record.canonical_entity_type = "order"
    raw_record.canonical_entity_id = order.id
    raw_record.save(update_fields=["status", "canonical_entity_type", "canonical_entity_id", "updated_at"])
    OutboxEvent.objects.get_or_create(
        company=connection.company, idempotency_key=f"order.ingested:{raw_record.id}",
        defaults={"topic": "order.ingested", "aggregate_type": "order", "aggregate_id": order.id, "payload": {"order_id": str(order.id), "source": connection.provider.key, "raw_record_id": str(raw_record.id)}},
    )
    return order


def _merge_supported_reference(connection, resource_type, data, raw_record):
    entity, canonical_type = None, resource_type.rstrip("s")
    if not connection.legacy_account:
        return None
    if resource_type == "returns":
        entity, canonical_type = _upsert_return(connection.legacy_account, data), "return"
    elif resource_type == "transactions":
        entity, canonical_type = _upsert_finance_entry(connection.legacy_account, data), "finance_entry"
    elif resource_type == "inventory":
        entity, canonical_type = _reconcile_external_inventory(connection.legacy_account, data, raw_record.id), "inventory_ledger"
    if entity:
        raw_record.canonical_entity_type, raw_record.canonical_entity_id = canonical_type, entity.id
        _attach_identity(connection, canonical_type, raw_record.external_id, raw_record.scope, canonical_type, entity.id)
    raw_record.status = "merged" if entity else "normalized"
    raw_record.save(update_fields=["status", "canonical_entity_type", "canonical_entity_id", "updated_at"])
    return entity


@transaction.atomic
def ingest_records(connection, resource_type, records, *, run=None, mapping_version=None):
    results = {"received": 0, "merged": 0, "duplicate": 0, "quarantined": 0, "errors": []}
    for index, record in enumerate(records):
        digest = payload_digest(record)
        external_id = str(record.get("external_id") or record.get("external_sku") or record.get("transactionId") or record.get("return_id") or record.get("id") or record.get("order_id") or f"row-{index + 1}")
        external_version = str(record.get("external_version") or record.get("updated_at") or "1")
        raw, created = RawRecord.objects.get_or_create(
            company=connection.company, connection=connection,
            object_type=resource_type.rstrip("s"), external_id=external_id,
            external_version=external_version, scope=str(record.get("marketplace", "")), payload_hash=digest,
            defaults={"ingestion_run": run, "event_time": parse_datetime(record.get("ordered_at")) if isinstance(record.get("ordered_at"), str) else record.get("ordered_at"), "payload": record, "mapping_version": mapping_version},
        )
        if not created:
            results["duplicate"] += 1
            continue
        results["received"] += 1
        normalized = record
        if mapping_version:
            normalized, errors = apply_mapping(record, mapping_version.rules, connection.company)
            if errors:
                raw.status, raw.error = "quarantined", json.dumps(errors, ensure_ascii=False)
                raw.save(update_fields=["status", "error", "updated_at"])
                results["quarantined"] += 1
                results["errors"].append({"external_id": external_id, "errors": errors})
                continue
            if resource_type == "orders":
                normalized = _canonical_order_payload(normalized)
        if resource_type == "orders":
            entity = _merge_order(connection, normalized, raw)
            results["merged" if entity else "quarantined"] += 1
        elif resource_type in {"returns", "transactions", "inventory"}:
            _merge_supported_reference(connection, resource_type, normalized, raw)
            results["merged"] += 1
        else:
            raw.status = "normalized"
            raw.save(update_fields=["status", "updated_at"])
            results["merged"] += 1
    if run:
        run.processed += results["received"] + results["duplicate"]
        run.succeeded += results["merged"]
        run.failed += results["quarantined"]
        run.save(update_fields=["processed", "succeeded", "failed", "updated_at"])
    return results


@transaction.atomic
def replay_raw_record(raw_record, mapping_version=None):
    version = mapping_version or raw_record.mapping_version
    normalized = raw_record.payload
    if version:
        normalized, errors = apply_mapping(raw_record.payload, version.rules, raw_record.company)
        if errors:
            raw_record.status, raw_record.error, raw_record.mapping_version = "quarantined", json.dumps(errors, ensure_ascii=False), version
            raw_record.save(update_fields=["status", "error", "mapping_version", "updated_at"])
            return {"merged": 0, "quarantined": 1, "errors": errors}
        if raw_record.object_type == "order":
            normalized = _canonical_order_payload(normalized)
    if raw_record.object_type == "order":
        entity = _merge_order(raw_record.connection, normalized, raw_record)
        raw_record.mapping_version = version
        raw_record.error = ""
        raw_record.save(update_fields=["mapping_version", "error", "updated_at"])
        return {"merged": int(bool(entity)), "quarantined": int(not entity), "entity_id": str(entity.id) if entity else None}
    raw_record.status, raw_record.mapping_version, raw_record.error = "normalized", version, ""
    raw_record.save(update_fields=["status", "mapping_version", "error", "updated_at"])
    return {"merged": 1, "quarantined": 0}


def run_ingestion(connection, resource_type="orders", mode="incremental", since=None, cursor=None, mapping_version=None):
    cursor_key = f"{mode}:{resource_type}:cursor"
    if cursor is None:
        cursor = connection.settings.get(cursor_key) or None
    run = IngestionRun.objects.create(
        connection=connection, resource_type=resource_type, mode=mode, status="running",
        cursor=cursor or "", range_start=since, started_at=timezone.now(),
    )
    try:
        connector = get_connector(connection)
        records, next_cursor = connector.pull_changes(resource_type, cursor=cursor, since=since)
        result = ingest_records(connection, resource_type, records, run=run, mapping_version=mapping_version)
        run.status, run.cursor, run.finished_at = ("paused" if mode == "backfill" and next_cursor else "succeeded"), next_cursor or "", timezone.now()
        settings = dict(connection.settings)
        if next_cursor:
            settings[cursor_key] = next_cursor
        else:
            settings.pop(cursor_key, None)
        connection.settings = settings
        connection.last_sync_at, connection.last_error = timezone.now(), ""
        connection.save(update_fields=["settings", "last_sync_at", "last_error", "updated_at"])
        return run, result
    except Exception as exc:
        run.status, run.error, run.finished_at = "failed", str(exc), timezone.now()
        connection.last_error = str(exc)
        connection.save(update_fields=["last_error", "updated_at"])
        raise
    finally:
        run.save(update_fields=["status", "cursor", "error", "finished_at", "processed", "succeeded", "failed", "updated_at"])
