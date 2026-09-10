from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import InventoryBalance, InventoryLedger
from .inventory import move_inventory


@transaction.atomic
def ship_transfer(transfer, actor=None):
    if transfer.status not in {"draft", "approved"}:
        raise ValidationError("当前调拨单不可发出")
    for item in transfer.items.select_related("sku"):
        source_balance = InventoryBalance.objects.select_for_update().filter(warehouse=transfer.source, sku=item.sku).first()
        if not source_balance or source_balance.available < item.quantity:
            raise ValidationError(f"SKU {item.sku.code} 调拨库存不足")
        move_inventory(company=transfer.company, warehouse=transfer.source, sku=item.sku,
            movement_type=InventoryLedger.Type.TRANSFER_OUT, quantity_delta=-item.quantity,
            reference_type="transfer", reference_id=transfer.id,
            idempotency_key=f"transfer-out:{transfer.id}:{item.id}", actor=actor)
        move_inventory(company=transfer.company, warehouse=transfer.destination, sku=item.sku,
            movement_type=InventoryLedger.Type.TRANSFER_IN, in_transit_delta=item.quantity,
            reference_type="transfer", reference_id=transfer.id,
            idempotency_key=f"transfer-transit:{transfer.id}:{item.id}", actor=actor)
    transfer.status = "in_transit"
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


@transaction.atomic
def receive_transfer(transfer, actor=None):
    if transfer.status != "in_transit":
        raise ValidationError("只有在途调拨单可以收货")
    for item in transfer.items.select_related("sku"):
        receive_qty = item.quantity - item.received_quantity
        if receive_qty <= 0:
            continue
        move_inventory(company=transfer.company, warehouse=transfer.destination, sku=item.sku,
            movement_type=InventoryLedger.Type.TRANSFER_IN, quantity_delta=receive_qty, in_transit_delta=-receive_qty,
            reference_type="transfer", reference_id=transfer.id,
            idempotency_key=f"transfer-receive:{transfer.id}:{item.id}", actor=actor)
        item.received_quantity += receive_qty
        item.save(update_fields=["received_quantity", "updated_at"])
    transfer.status = "completed"
    transfer.save(update_fields=["status", "updated_at"])
    return transfer
