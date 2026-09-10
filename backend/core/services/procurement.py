from decimal import Decimal

from django.db import transaction

from core.models import InventoryLedger, PurchaseOrder, Receipt
from .inventory import move_inventory


@transaction.atomic
def post_receipt(receipt, actor=None):
    if receipt.posted:
        return receipt
    items = list(receipt.items.select_related("purchase_order_item__sku"))
    weights = []
    for item in items:
        sku = item.purchase_order_item.sku
        if receipt.allocation_method == "weight":
            weight = sku.gross_weight_kg * item.quantity
        elif receipt.allocation_method == "volume":
            weight = sku.volume_cbm * item.quantity
        elif receipt.allocation_method == "value":
            weight = item.unit_cost * item.quantity
        else:
            weight = item.quantity
        weights.append(max(weight, Decimal("0")))
    denominator = sum(weights, Decimal("0")) or Decimal("1")
    for item, weight in zip(items, weights):
        allocation = receipt.landed_cost * weight / denominator
        item.allocated_landed_cost = allocation
        landed_unit = allocation / item.quantity if item.quantity else 0
        item.save(update_fields=["allocated_landed_cost", "updated_at"])
        po_item = item.purchase_order_item
        unit_cost = item.unit_cost + landed_unit
        move_inventory(
            company=receipt.company, warehouse=receipt.warehouse, sku=po_item.sku,
            movement_type=InventoryLedger.Type.PURCHASE_RECEIPT, quantity_delta=item.quantity,
            unit_cost=unit_cost, reference_type="receipt", reference_id=receipt.id,
            idempotency_key=f"receipt:{receipt.id}:{item.id}", actor=actor,
        )
        po_item.received_quantity += item.quantity
        po_item.save(update_fields=["received_quantity", "updated_at"])
    receipt.posted = True
    receipt.save(update_fields=["posted", "updated_at"])
    po = receipt.purchase_order
    all_received = all(i.received_quantity >= i.quantity for i in po.items.all())
    po.status = PurchaseOrder.Status.COMPLETED if all_received else PurchaseOrder.Status.PARTIAL
    po.save(update_fields=["status", "updated_at"])
    return receipt

