from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.models import FinanceEntry, InventoryBalance, Order, OrderItem, ReturnOrder
from .finance import COST_TYPES


MONEY_FIELD = DecimalField(max_digits=24, decimal_places=4)


def _decimal(value):
    return value or Decimal("0")


def _period(params):
    days = max(1, min(int(params.get("days", 30) or 30), 730))
    today = timezone.localdate()
    date_to = parse_date(params.get("date_to", "")) or today
    date_from = parse_date(params.get("date_from", "")) or (date_to - timedelta(days=days - 1))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to, (date_to - date_from).days + 1


def _apply_order_filters(queryset, params):
    if params.get("channel"):
        queryset = queryset.filter(store__account__provider=params["channel"])
    if params.get("store"):
        queryset = queryset.filter(store_id=params["store"])
    if params.get("country"):
        queryset = queryset.filter(store__country=params["country"])
    if params.get("sku"):
        queryset = queryset.filter(items__sku_id=params["sku"])
    return queryset.distinct()


def workbench(company, params=None):
    params = params or {}
    date_from, date_to, days = _period(params)
    orders = _apply_order_filters(
        Order.objects.filter(company=company, ordered_at__date__gte=date_from, ordered_at__date__lte=date_to), params
    )
    items = OrderItem.objects.filter(order__in=orders)
    inventory = InventoryBalance.objects.filter(company=company).select_related("warehouse", "sku")
    if params.get("warehouse"):
        inventory = inventory.filter(warehouse_id=params["warehouse"])
    if params.get("sku"):
        inventory = inventory.filter(sku_id=params["sku"])

    entries = FinanceEntry.objects.filter(company=company, occurred_at__date__gte=date_from, occurred_at__date__lte=date_to)
    if any(params.get(key) for key in ("channel", "store", "country", "sku")):
        entries = entries.filter(order__in=orders)

    revenue = _decimal(entries.filter(entry_type=FinanceEntry.Type.REVENUE).aggregate(v=Sum("base_amount"))["v"])
    costs = _decimal(entries.filter(entry_type__in=COST_TYPES).aggregate(v=Sum("base_amount"))["v"])
    gmv = _decimal(orders.aggregate(v=Sum("total"))["v"])
    units = _decimal(items.aggregate(v=Sum("quantity"))["v"])
    order_count = orders.count()
    returns = ReturnOrder.objects.filter(company=company, order__in=orders)
    refund = _decimal(returns.aggregate(v=Sum("refund_amount"))["v"])
    contribution = revenue - costs

    inventory_totals = inventory.aggregate(on_hand=Sum("on_hand"), reserved=Sum("reserved"), in_transit=Sum("in_transit"), damaged=Sum("damaged"))
    inventory_totals = {key: _decimal(value) for key, value in inventory_totals.items()}
    inventory_totals["available"] = inventory_totals["on_hand"] - inventory_totals["reserved"] - inventory_totals["damaged"]
    inventory_value = sum((row.on_hand * row.average_cost for row in inventory), Decimal("0"))

    line_value = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=MONEY_FIELD)
    channels = list(orders.values(key=F("store__account__provider")).annotate(orders=Count("id", distinct=True), gmv=Sum("total")).order_by("-gmv"))
    stores = list(orders.values(key=F("store_id"), name=F("store__name")).annotate(orders=Count("id", distinct=True), gmv=Sum("total")).order_by("-gmv")[:20])
    countries = list(orders.values(key=F("store__country")).annotate(orders=Count("id", distinct=True), gmv=Sum("total")).order_by("-gmv"))
    top_skus = list(
        items.exclude(sku=None)
        .values(key=F("sku_id"), code=F("sku__code"), name=F("sku__name"))
        .annotate(sales=Sum(line_value))
        .annotate(quantity=Sum("quantity"))
        .order_by("-sales")[:20]
    )
    trend_rows = list(orders.annotate(day=TruncDate("ordered_at")).values("day").annotate(orders=Count("id", distinct=True), gmv=Sum("total")).order_by("day"))
    finance_trend = {
        row["day"]: row for row in entries.annotate(day=TruncDate("occurred_at")).values("day").annotate(
            revenue=Sum("base_amount", filter=Q(entry_type=FinanceEntry.Type.REVENUE)),
            cost=Sum("base_amount", filter=Q(entry_type__in=COST_TYPES)),
        )
    }
    trend = []
    for row in trend_rows:
        finance = finance_trend.get(row["day"], {})
        day_revenue, day_cost = _decimal(finance.get("revenue")), _decimal(finance.get("cost"))
        trend.append({**row, "revenue": day_revenue, "cost": day_cost, "profit": day_revenue - day_cost})

    warehouse_rows = []
    for row in inventory.values("warehouse_id", "warehouse__name", "warehouse__country").annotate(
        on_hand=Sum("on_hand"), reserved=Sum("reserved"), in_transit=Sum("in_transit"), damaged=Sum("damaged")
    ).order_by("warehouse__name"):
        row["available"] = _decimal(row["on_hand"]) - _decimal(row["reserved"]) - _decimal(row["damaged"])
        warehouse_rows.append(row)

    finance_breakdown = list(entries.values(key=F("entry_type")).annotate(amount=Sum("base_amount"), count=Count("id")).order_by("-amount"))
    return_status = list(returns.values(key=F("status")).annotate(count=Count("id"), refund=Sum("refund_amount")).order_by("-count"))
    return_reasons = list(returns.values(key=F("reason")).annotate(count=Count("id"), refund=Sum("refund_amount")).order_by("-count")[:10])
    order_status = list(orders.values(key=F("status")).annotate(count=Count("id"), gmv=Sum("total")).order_by("-count"))

    return {
        "period": {"date_from": date_from, "date_to": date_to, "days": days},
        "currency": company.base_currency,
        "kpis": {
            "gmv": gmv, "net_revenue": revenue, "cost": costs, "contribution_profit": contribution,
            "contribution_margin": round((contribution / revenue * 100), 2) if revenue else Decimal("0"),
            "orders": order_count, "units": units, "average_order_value": gmv / order_count if order_count else Decimal("0"),
            "returns": returns.count(), "return_rate": round((Decimal(returns.count()) / order_count * 100), 2) if order_count else Decimal("0"),
            "refund": refund, "inventory_value": inventory_value,
        },
        "inventory": inventory_totals, "trend": trend, "channels": channels, "stores": stores,
        "countries": countries, "top_skus": top_skus, "warehouse_inventory": warehouse_rows,
        "finance_breakdown": finance_breakdown, "order_status": order_status,
        "return_status": return_status, "return_reasons": return_reasons,
        "filter_options": {
            "channels": list(company.channel_accounts.values_list("provider", flat=True).distinct().order_by("provider")),
            "stores": list(company.stores.filter(is_active=True).values("id", "name", "country").order_by("name")),
            "countries": list(company.stores.values_list("country", flat=True).distinct().order_by("country")),
            "warehouses": list(company.warehouses.filter(is_active=True).values("id", "name", "country").order_by("name")),
            "skus": list(company.skus.filter(is_active=True).values("id", "code", "name").order_by("code")[:500]),
        },
        "metric_version": 1, "field_definition_version": "1.0",
        "source_summary": ["canonical.orders", "canonical.inventory", "canonical.finance", "semantic.v1"],
        "updated_at": timezone.now(),
    }


def overview(company, days=30):
    data = workbench(company, {"days": days})
    return {
        "period_days": data["period"]["days"], "currency": data["currency"],
        "gmv_original": data["kpis"]["gmv"], "revenue_cny": data["kpis"]["net_revenue"],
        "cost_cny": data["kpis"]["cost"], "contribution_profit_cny": data["kpis"]["contribution_profit"],
        "return_count": data["kpis"]["returns"], "refund_original": data["kpis"]["refund"],
        "inventory": data["inventory"], "channels": data["channels"], "top_skus": data["top_skus"],
        "trend": data["trend"], "metric_version": data["metric_version"],
    }
