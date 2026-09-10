from decimal import Decimal

from django.db.models import Sum

from core.models import FinanceEntry


COST_TYPES = {
    FinanceEntry.Type.PRODUCT_COST, FinanceEntry.Type.COMMISSION, FinanceEntry.Type.STORAGE,
    FinanceEntry.Type.LAST_MILE, FinanceEntry.Type.FIRST_MILE, FinanceEntry.Type.DUTY,
    FinanceEntry.Type.VAT, FinanceEntry.Type.COUPON, FinanceEntry.Type.ADVERTISING,
    FinanceEntry.Type.REFUND, FinanceEntry.Type.RETURN_LOSS, FinanceEntry.Type.OTHER,
}


def order_profit(order):
    grouped = order.finance_entries.values("entry_type").annotate(total=Sum("base_amount"))
    values = {row["entry_type"]: row["total"] or Decimal("0") for row in grouped}
    revenue = values.get(FinanceEntry.Type.REVENUE, Decimal("0"))
    costs = sum((values.get(kind, Decimal("0")) for kind in COST_TYPES), Decimal("0"))
    return {"revenue": revenue, "costs": costs, "contribution_profit": revenue - costs, "breakdown": values}

