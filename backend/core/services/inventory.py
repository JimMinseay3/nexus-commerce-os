from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from core.models import InventoryBalance, InventoryLedger


def _d(value):
    return Decimal(str(value))


@transaction.atomic
def move_inventory(*, company, warehouse, sku, movement_type, quantity_delta=0, reserved_delta=0,
                   in_transit_delta=0, damaged_delta=0, unit_cost=0, reference_type="", reference_id="",
                   idempotency_key, note="", actor=None):
    existing = InventoryLedger.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    balance, _ = InventoryBalance.objects.select_for_update().get_or_create(
        company=company, warehouse=warehouse, sku=sku,
        defaults={"on_hand": 0, "reserved": 0, "damaged": 0, "average_cost": unit_cost},
    )
    quantity_delta, reserved_delta = _d(quantity_delta), _d(reserved_delta)
    in_transit_delta = _d(in_transit_delta)
    damaged_delta, unit_cost = _d(damaged_delta), _d(unit_cost)
    new_on_hand = balance.on_hand + quantity_delta
    new_reserved = balance.reserved + reserved_delta
    new_in_transit = balance.in_transit + in_transit_delta
    new_damaged = balance.damaged + damaged_delta
    if min(new_on_hand, new_reserved, new_in_transit, new_damaged) < 0:
        raise ValidationError("库存、预占、在途或残次数量不能为负数")
    if new_reserved + new_damaged > new_on_hand:
        raise ValidationError("预占与残次库存不能超过现有库存")

    if quantity_delta > 0 and unit_cost >= 0:
        old_value = balance.on_hand * balance.average_cost
        balance.average_cost = (old_value + quantity_delta * unit_cost) / new_on_hand if new_on_hand else 0
    balance.on_hand = new_on_hand
    balance.reserved = new_reserved
    balance.in_transit = new_in_transit
    balance.damaged = new_damaged
    balance.save(update_fields=["on_hand", "reserved", "in_transit", "damaged", "average_cost", "updated_at"])
    if quantity_delta > 0 and unit_cost >= 0:
        weighted, total = Decimal("0"), Decimal("0")
        for row in InventoryBalance.objects.filter(company=company, sku=sku):
            weighted += row.on_hand * row.average_cost
            total += row.on_hand
        if total > 0:
            sku.moving_average_cost = weighted / total
            sku.save(update_fields=["moving_average_cost", "updated_at"])
    ledger = InventoryLedger.objects.create(
        company=company, warehouse=warehouse, sku=sku, movement_type=movement_type,
        quantity_delta=quantity_delta, reserved_delta=reserved_delta, in_transit_delta=in_transit_delta, damaged_delta=damaged_delta,
        unit_cost=unit_cost, reference_type=reference_type, reference_id=str(reference_id),
        idempotency_key=idempotency_key, note=note, actor=actor,
    )
    from core.tasks import deliver_webhook_event
    transaction.on_commit(lambda: deliver_webhook_event.delay("inventory.changed", {
        "ledger_id": ledger.id, "warehouse_id": str(warehouse.id), "sku_id": str(sku.id),
        "sku": sku.code, "on_hand": str(balance.on_hand), "reserved": str(balance.reserved),
        "in_transit": str(balance.in_transit), "damaged": str(balance.damaged), "available": str(balance.available),
    }, str(company.id)))
    return ledger, True



def reserve(*, balance, quantity, reference_type, reference_id, actor=None):
    quantity = _d(quantity)
    if balance.available < quantity:
        raise ValidationError(f"SKU {balance.sku.code} 可用库存不足")
    return move_inventory(
        company=balance.company, warehouse=balance.warehouse, sku=balance.sku,
        movement_type=InventoryLedger.Type.SALE_RESERVE, reserved_delta=quantity,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=f"reserve:{reference_type}:{reference_id}:{balance.warehouse_id}:{balance.sku_id}", actor=actor,
    )


def ship(*, balance, quantity, reference_id, actor=None):
    quantity = _d(quantity)
    return move_inventory(
        company=balance.company, warehouse=balance.warehouse, sku=balance.sku,
        movement_type=InventoryLedger.Type.SALE_SHIP, quantity_delta=-quantity, reserved_delta=-quantity,
        reference_type="shipment", reference_id=reference_id,
        idempotency_key=f"ship:{reference_id}:{balance.warehouse_id}:{balance.sku_id}", actor=actor,
    )
