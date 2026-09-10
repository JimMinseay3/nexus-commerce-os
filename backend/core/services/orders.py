from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import Allocation, FinanceEntry, InventoryBalance, Order, Shipment
from .inventory import reserve, ship


@transaction.atomic
def allocate_order(order, actor=None):
    if order.status not in {Order.Status.PENDING, Order.Status.ALLOCATING, Order.Status.BACKORDER}:
        raise ValidationError("当前订单状态不可分配")
    order.status = Order.Status.ALLOCATING
    order.save(update_fields=["status", "updated_at"])
    complete = True
    for item in order.items.select_related("sku"):
        if not item.sku:
            complete = False
            continue
        already = sum((x.quantity - x.released_quantity for x in item.allocations.all()), Decimal("0"))
        remaining = item.quantity - already
        if remaining <= 0:
            continue
        balances = list(InventoryBalance.objects.select_for_update().filter(
            company=order.company, sku=item.sku, warehouse__is_active=True,
        ).select_related("warehouse").order_by("warehouse__priority"))
        for balance in balances:
            take = min(max(balance.available, Decimal("0")), remaining)
            if take <= 0:
                continue
            allocation = Allocation.objects.create(order_item=item, warehouse=balance.warehouse, quantity=take)
            reserve(balance=balance, quantity=take, reference_type="allocation", reference_id=allocation.id, actor=actor)
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            complete = False
    order.status = Order.Status.PICKING if complete else Order.Status.BACKORDER
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def post_shipment(shipment, actor=None):
    if shipment.status == Shipment.Status.SHIPPED:
        return shipment
    for package in shipment.packages.prefetch_related("items__order_item__allocations", "items__order_item__sku"):
        for shipment_item in package.items.all():
            allocation = shipment_item.order_item.allocations.filter(warehouse=shipment.warehouse).first()
            if not allocation:
                raise ValidationError(f"订单行 {shipment_item.order_item_id} 未在该仓库预占")
            balance = InventoryBalance.objects.select_for_update().get(warehouse=shipment.warehouse, sku=shipment_item.order_item.sku)
            unit_cost = balance.average_cost
            ship(balance=balance, quantity=shipment_item.quantity, reference_id=shipment.id, actor=actor)
            product_cost = unit_cost * shipment_item.quantity
            FinanceEntry.objects.get_or_create(
                company=shipment.company,
                external_id=f"shipment-cost:{shipment.id}:{shipment_item.id}",
                defaults={
                    "entry_type": FinanceEntry.Type.PRODUCT_COST, "occurred_at": timezone.now(),
                    "order": shipment.order, "currency": shipment.company.base_currency,
                    "amount": product_cost, "exchange_rate": 1, "base_amount": product_cost,
                    "note": f"发货成本 {shipment.shipment_no}",
                },
            )
            shipment_item.order_item.shipped_quantity += shipment_item.quantity
            shipment_item.order_item.save(update_fields=["shipped_quantity", "updated_at"])
    shipment.status = Shipment.Status.SHIPPED
    shipment.shipped_at = timezone.now()
    shipment.save(update_fields=["status", "shipped_at", "updated_at"])
    order = shipment.order
    # Aggregate from the database so a prefetched Order instance cannot make the
    # status calculation read stale shipped_quantity values.
    totals = order.items.aggregate(total=Sum("quantity"), shipped=Sum("shipped_quantity"))
    total = totals["total"] or Decimal("0")
    shipped = totals["shipped"] or Decimal("0")
    order.status = Order.Status.SHIPPED if shipped >= total else Order.Status.PARTIALLY_SHIPPED
    order.save(update_fields=["status", "updated_at"])
    return shipment
