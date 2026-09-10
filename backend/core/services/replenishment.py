import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from core.models import InventoryBalance, OrderItem, PurchaseOrderItem, ReplenishmentSuggestion


def generate_for_company(company, window_days=30):
    since = timezone.now() - timedelta(days=window_days)
    generated = []
    for balance in InventoryBalance.objects.filter(company=company, warehouse__is_active=True).select_related("sku", "warehouse"):
        sku = balance.sku
        sold = OrderItem.objects.filter(
            sku=sku, order__company=company, order__ordered_at__gte=since,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        velocity = sold / Decimal(window_days)
        lead_days = sku.purchase_lead_days + sku.production_lead_days + sku.ocean_lead_days
        target = velocity * Decimal(lead_days) + Decimal(sku.safety_stock)
        inbound = PurchaseOrderItem.objects.filter(
            sku=sku,
            purchase_order__warehouse=balance.warehouse,
            purchase_order__status__in=["ordered", "production", "in_transit", "partial"],
        ).aggregate(total=Sum("quantity") - Sum("received_quantity"))["total"] or Decimal("0")
        shortage = target - balance.available - inbound
        if shortage <= 0:
            continue
        pack = max(sku.case_pack, sku.moq, 1)
        suggested = Decimal(math.ceil(float(shortage) / pack) * pack)
        stockout = timezone.localdate() + timedelta(days=int(balance.available / velocity)) if velocity > 0 else None
        obj, _ = ReplenishmentSuggestion.objects.update_or_create(
            company=company, sku=sku, warehouse=balance.warehouse, status=ReplenishmentSuggestion.Status.OPEN,
            defaults={
                "sales_window_days": window_days,
                "daily_velocity": velocity,
                "suggested_quantity": suggested,
                "expected_stockout_at": stockout,
                "suggested_order_at": (stockout - timedelta(days=lead_days)) if stockout else timezone.localdate(),
                "explanation": {
                    "available": str(balance.available), "inbound": str(inbound), "sales": str(sold),
                    "lead_days": lead_days, "safety_stock": sku.safety_stock, "case_pack": pack,
                },
            },
        )
        generated.append(obj)
    return generated

