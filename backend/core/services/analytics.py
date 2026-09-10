from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import FinanceEntry, InventoryBalance, Order, OrderItem, PurchaseOrderItem, ReturnOrder
from .finance import COST_TYPES


def overview(company, days=30):
    since = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(company=company, ordered_at__gte=since)
    entries = FinanceEntry.objects.filter(company=company, occurred_at__gte=since)
    revenue = entries.filter(entry_type=FinanceEntry.Type.REVENUE).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
    costs = entries.filter(entry_type__in=COST_TYPES).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
    gross = orders.aggregate(v=Sum("total"))["v"] or Decimal("0")
    returns = ReturnOrder.objects.filter(company=company, created_at__gte=since).aggregate(count=Count("id"), amount=Sum("refund_amount"))
    inventory = InventoryBalance.objects.filter(company=company).aggregate(on_hand=Sum("on_hand"), reserved=Sum("reserved"), in_transit=Sum("in_transit"), damaged=Sum("damaged"))
    channel_rows = list(orders.values("store__account__provider").annotate(orders=Count("id"), gmv=Sum("total")).order_by("store__account__provider"))
    sku_rows = list(OrderItem.objects.filter(order__in=orders).values("sku__code", "sku__name").annotate(quantity=Sum("quantity"), sales=Sum("order__total")).order_by("-quantity")[:20])
    trend = list(orders.annotate(day=TruncDate("ordered_at")).values("day").annotate(orders=Count("id"), gmv=Sum("total")).order_by("day"))
    return {
        "period_days": days, "currency": company.base_currency, "gmv_original": gross,
        "revenue_cny": revenue, "cost_cny": costs, "contribution_profit_cny": revenue - costs,
        "return_count": returns["count"], "refund_original": returns["amount"] or Decimal("0"),
        "inventory": inventory, "channels": channel_rows, "top_skus": sku_rows, "trend": trend,
        "metric_version": 1,
    }


def procurement_unused():
    # Kept as an explicit boundary for future materialized fact refresh tasks.
    return PurchaseOrderItem.objects.none()
