from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.connectors import get_connector
from core.models import (
    ChannelSKU, FinanceEntry, InventoryBalance, InventoryLedger, Order, OrderItem,
    ReturnItem, ReturnOrder, Store, SyncJob, Warehouse,
)
from .inventory import move_inventory


def _decimal(value):
    return Decimal(str(value or 0))


@transaction.atomic
def upsert_normalized_order(account, data):
    store = Store.objects.filter(account=account, marketplace=data.get("marketplace")).first() or Store.objects.filter(account=account).first()
    if not store:
        raise ValueError("平台账号尚未配置店铺")
    ordered_at = data.get("ordered_at")
    if isinstance(ordered_at, str):
        ordered_at = parse_datetime(ordered_at)
    ordered_at = ordered_at or timezone.now()
    order, _ = Order.objects.update_or_create(
        store=store, external_id=data["external_id"],
        defaults={
            "company": account.company, "external_version": data.get("external_version", "1"),
            "status": data.get("status", Order.Status.PENDING), "fulfillment": data.get("fulfillment", "fbm"),
            "ordered_at": ordered_at, "buyer_name": data.get("buyer_name", ""), "buyer_email": data.get("buyer_email", ""),
            "ship_to": data.get("ship_to", {}), "currency": data.get("currency", store.currency),
            "subtotal": _decimal(data.get("subtotal")), "shipping_income": _decimal(data.get("shipping_income")),
            "tax": _decimal(data.get("tax")), "discount": _decimal(data.get("discount")), "total": _decimal(data.get("total")),
            "raw_payload": data.get("raw", data),
        },
    )
    for row in data.get("items", []):
        external_sku = row.get("external_sku") or row.get("SellerSKU") or row.get("sku") or ""
        mapping = ChannelSKU.objects.filter(store=store, external_sku=external_sku).select_related("sku").first()
        OrderItem.objects.update_or_create(
            order=order, external_line_id=str(row.get("external_line_id") or row.get("OrderItemId") or row.get("lineNumber")),
            defaults={
                "sku": mapping.sku if mapping else None, "external_sku": external_sku,
                "title": row.get("title") or row.get("Title", ""), "quantity": _decimal(row.get("quantity") or row.get("QuantityOrdered")),
                "unit_price": _decimal(row.get("unit_price")), "tax": _decimal(row.get("tax")), "discount": _decimal(row.get("discount")),
            },
        )
    return order


def sync_account(account, job_type="orders", since=None):
    connector = get_connector(account)
    job = SyncJob.objects.create(account=account, job_type=job_type, status="running", started_at=timezone.now())
    try:
        cursor = account.settings.get(f"{job_type}_cursor")
        if job_type == "orders":
            records, next_cursor = connector.pull_orders(cursor=cursor, since=since)
            for record in records:
                upsert_normalized_order(account, record)
        elif job_type == "returns":
            records, next_cursor = connector.pull_returns(cursor=cursor, since=since)
            for record in records:
                _upsert_return(account, record)
        elif job_type == "inventory":
            records, next_cursor = connector.pull_inventory(cursor=cursor)
            for record in records:
                _reconcile_external_inventory(account, record, job.id)
        elif job_type == "transactions":
            records, next_cursor = connector.pull_transactions(cursor=cursor, since=since)
            for record in records:
                _upsert_finance_entry(account, record)
        elif job_type == "settlements":
            records, next_cursor = connector.pull_settlements(cursor=cursor, since=since)
        else:
            raise ValueError(f"不支持的同步类型: {job_type}")
        settings = account.settings.copy()
        if next_cursor:
            settings[f"{job_type}_cursor"] = next_cursor
        account.settings = settings
        account.last_sync_at = timezone.now()
        account.last_error = ""
        account.save(update_fields=["settings", "last_sync_at", "last_error", "updated_at"])
        job.status, job.processed, job.cursor = "succeeded", len(records), next_cursor or ""
        return job
    except Exception as exc:
        account.last_error = str(exc)
        account.save(update_fields=["last_error", "updated_at"])
        job.status, job.failed, job.error = "failed", 1, str(exc)
        raise
    finally:
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "processed", "failed", "cursor", "error", "finished_at", "updated_at"])


def _reconcile_external_inventory(account, record, sync_job_id):
    mapping = ChannelSKU.objects.filter(store__account=account, external_sku=record.get("external_sku"), is_active=True).select_related("sku").first()
    if not mapping:
        return None
    warehouse_id = account.settings.get("warehouse_id")
    warehouse = Warehouse.objects.filter(company=account.company, pk=warehouse_id).first() if warehouse_id else None
    warehouse = warehouse or Warehouse.objects.filter(company=account.company, type=Warehouse.Type.PLATFORM, fulfillment_node=record.get("node", "")).first()
    if not warehouse:
        warehouse = Warehouse.objects.create(
            company=account.company, code=f"{account.provider[:3].upper()}-{str(account.id)[:6]}",
            name=f"{account.get_provider_display()} 平台仓", type=Warehouse.Type.PLATFORM,
            country=account.stores.first().country if account.stores.exists() else "US",
            owner=account.get_provider_display(), fulfillment_node=record.get("node", ""), priority=200,
        )
    target = _decimal(record.get("quantity"))
    balance = InventoryBalance.objects.filter(warehouse=warehouse, sku=mapping.sku).first()
    current = balance.on_hand if balance else Decimal("0")
    delta = target - current
    if not delta:
        return None
    ledger, _ = move_inventory(
        company=account.company, warehouse=warehouse, sku=mapping.sku,
        movement_type=InventoryLedger.Type.EXTERNAL_SYNC, quantity_delta=delta,
        unit_cost=mapping.sku.moving_average_cost, reference_type="channel_inventory", reference_id=account.id,
        idempotency_key=f"channel-stock:{sync_job_id}:{record.get('node','')}:{mapping.sku_id}:{target}",
        note="平台仓库存对账",
    )
    return ledger


def _upsert_return(account, raw):
    external_id = str(raw.get("returnOrderId") or raw.get("return_id") or raw.get("id") or "")
    order_id = str(raw.get("purchaseOrderId") or raw.get("orderId") or raw.get("order_id") or "")
    order = Order.objects.filter(company=account.company, store__account=account, external_id=order_id).first()
    if not external_id or not order:
        return None
    return_order, _ = ReturnOrder.objects.update_or_create(
        company=account.company, external_id=external_id,
        defaults={"order": order, "status": "requested", "reason": raw.get("reason", ""), "currency": order.currency, "refund_amount": _decimal(raw.get("refundAmount")), "raw_payload": raw},
    )
    for index, line in enumerate(raw.get("items", raw.get("returnOrderLines", []))):
        external_line = str(line.get("lineNumber") or line.get("orderLineId") or index + 1)
        order_item = order.items.filter(external_line_id=external_line).first()
        if order_item:
            ReturnItem.objects.update_or_create(return_order=return_order, order_item=order_item, defaults={"quantity": _decimal(line.get("quantity", 1))})
    return return_order


def _upsert_finance_entry(account, raw):
    external_id = str(raw.get("transactionId") or raw.get("id") or raw.get("referenceId") or "")
    if not external_id:
        return None
    transaction_type = str(raw.get("transactionType") or raw.get("type") or "other").lower()
    kind = FinanceEntry.Type.REVENUE if any(x in transaction_type for x in ["sale", "charge", "revenue"]) else FinanceEntry.Type.REFUND if "refund" in transaction_type else FinanceEntry.Type.COMMISSION if "fee" in transaction_type else FinanceEntry.Type.OTHER
    amount_data = raw.get("totalAmount") or raw.get("amount") or {}
    amount = _decimal(amount_data.get("amount") if isinstance(amount_data, dict) else amount_data)
    currency = (amount_data.get("currencyCode") if isinstance(amount_data, dict) else None) or raw.get("currency", "USD")
    related = raw.get("relatedIdentifiers", [])
    order_external = raw.get("orderId") or next((x.get("value") for x in related if str(x.get("type", "")).lower().startswith("order")), None)
    order = Order.objects.filter(company=account.company, store__account=account, external_id=order_external).first() if order_external else None
    occurred = raw.get("postedDate") or raw.get("occurred_at")
    occurred = parse_datetime(occurred) if isinstance(occurred, str) else occurred
    entry, _ = FinanceEntry.objects.update_or_create(
        company=account.company, external_id=f"{account.id}:{external_id}",
        defaults={"entry_type": kind, "occurred_at": occurred or timezone.now(), "order": order, "currency": currency, "amount": abs(amount), "exchange_rate": 1, "base_amount": abs(amount), "note": f"{account.get_provider_display()} 自动同步"},
    )
    return entry
