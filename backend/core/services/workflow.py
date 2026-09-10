"""NEXUS demo workflow orchestration.

The simulator writes through the same domain services used by real connectors,
so it can validate a deployment before production credentials are available.
"""

from datetime import timedelta
from decimal import Decimal
import uuid

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.connectors import get_connector
from core.models import (
    ChannelAccount, ChannelSKU, ExchangeRate, FinanceEntry, InventoryBalance,
    InventoryLedger, Order, Package, Product, PurchaseOrder, PurchaseOrderItem,
    Receipt, ReceiptItem, ReplenishmentSuggestion, ReturnItem, ReturnOrder,
    Settlement, Shipment, ShipmentItem, SKU, Store, Supplier, SyncJob, Warehouse,
)

from .inventory import move_inventory
from .orders import allocate_order, post_shipment
from .procurement import post_receipt
from .replenishment import generate_for_company
from .sync import upsert_normalized_order


RATE = Decimal("7.20")
PROVIDERS = (
    ("amazon", "Amazon US", "ATVPDKIKX0DER"),
    ("wayfair", "Wayfair Dropship", "US"),
    ("walmart", "Walmart US", "US"),
)
SKU_BLUEPRINTS = (
    {"code": "NEX-CHAIR-OAK", "spu": "NEX-CHAIR", "product": "Aster 橡木餐椅", "name": "Aster 橡木餐椅 · 原木色", "price": Decimal("399"), "cost": Decimal("168"), "weight": Decimal("12.5"), "dimensions": (Decimal("82"), Decimal("52"), Decimal("47")), "safety": 30, "moq": 20, "case": 2},
    {"code": "NEX-DESK-WALNUT", "spu": "NEX-DESK", "product": "Atlas 胡桃木书桌", "name": "Atlas 胡桃木书桌 · 140cm", "price": Decimal("899"), "cost": Decimal("386"), "weight": Decimal("31.2"), "dimensions": (Decimal("148"), Decimal("76"), Decimal("18")), "safety": 18, "moq": 10, "case": 1},
    {"code": "NEX-LAMP-ARC", "spu": "NEX-LAMP", "product": "Luma 弧形落地灯", "name": "Luma 弧形落地灯 · 哑光黑", "price": Decimal("259"), "cost": Decimal("92"), "weight": Decimal("8.4"), "dimensions": (Decimal("112"), Decimal("38"), Decimal("24")), "safety": 36, "moq": 24, "case": 2},
)


def _foundation(company, actor=None):
    supplier, _ = Supplier.objects.get_or_create(
        company=company, code="NEX-SUP-001",
        defaults={"name": "NEXUS 家居智造伙伴", "contact_name": "林经理", "currency": "CNY", "payment_terms_days": 30, "default_lead_time_days": 28, "performance_score": Decimal("96.8")},
    )
    cn, _ = Warehouse.objects.get_or_create(
        company=company, code="NEX-CN-SZ",
        defaults={"name": "深圳中心仓", "type": Warehouse.Type.DOMESTIC, "country": "CN", "priority": 20},
    )
    us, _ = Warehouse.objects.get_or_create(
        company=company, code="NEX-US-LA",
        defaults={"name": "洛杉矶履约仓", "type": Warehouse.Type.OVERSEAS, "country": "US", "priority": 10},
    )

    skus = []
    for blueprint in SKU_BLUEPRINTS:
        product, _ = Product.objects.get_or_create(
            company=company, spu=blueprint["spu"],
            defaults={"name": blueprint["product"], "status": Product.Status.ACTIVE, "description": "NEXUS 全链路模拟商品", "attributes": {"collection": "NEXUS Launch", "demo": True}},
        )
        sku, _ = SKU.objects.get_or_create(
            company=company, code=blueprint["code"],
            defaults={
                "product": product, "name": blueprint["name"], "supplier": supplier,
                "supplier_sku": f"SUP-{blueprint['code']}", "purchase_price": blueprint["cost"],
                "moving_average_cost": blueprint["cost"], "gross_weight_kg": blueprint["weight"],
                "length_cm": blueprint["dimensions"][0], "width_cm": blueprint["dimensions"][1],
                "height_cm": blueprint["dimensions"][2], "safety_stock": blueprint["safety"],
                "moq": blueprint["moq"], "case_pack": blueprint["case"], "purchase_lead_days": 12,
                "production_lead_days": 18, "ocean_lead_days": 25, "first_mile_mode": "海运整柜",
                "tax_attributes": {"vat": True, "duty_rate": "0.08"},
            },
        )
        skus.append(sku)
        for warehouse, quantity, premium in ((cn, Decimal("72"), Decimal("0")), (us, Decimal("16"), Decimal("64"))):
            move_inventory(
                company=company, warehouse=warehouse, sku=sku,
                movement_type=InventoryLedger.Type.OPENING, quantity_delta=quantity,
                unit_cost=blueprint["cost"] + premium, reference_type="nexus_demo", reference_id="foundation",
                idempotency_key=f"nexus:opening:{company.id}:{warehouse.code}:{sku.code}",
                note="NEXUS 演示期初库存", actor=actor,
            )

    accounts = []
    for provider, name, marketplace in PROVIDERS:
        account, _ = ChannelAccount.objects.get_or_create(
            company=company, provider=provider, name=name,
            defaults={
                "environment": ChannelAccount.Environment.SANDBOX, "region": "NA",
                "settings": {"use_mock": True, "marketplace": marketplace, "demo_sku": skus[0].code},
                "capabilities": ["orders", "inventory", "shipments", "returns", "transactions", "settlements"],
                "is_enabled": True,
            },
        )
        if not account.is_enabled:
            account.is_enabled = True
            account.save(update_fields=["is_enabled", "updated_at"])
        store, _ = Store.objects.get_or_create(
            company=company, account=account, external_id=f"nexus-{provider}",
            defaults={"name": name, "marketplace": marketplace, "country": "US", "currency": "USD"},
        )
        for sku in skus:
            ChannelSKU.objects.get_or_create(
                sku=sku, store=store, external_sku=sku.code,
                defaults={"fulfillment": SKU.Fulfillment.FBM, "inventory_buffer": 3},
            )
        accounts.append(account)

    ExchangeRate.objects.get_or_create(
        company=company, rate_date=timezone.localdate(), from_currency="USD", to_currency="CNY",
        defaults={"rate": RATE, "source": "NEXUS simulator"},
    )
    return {"supplier": supplier, "warehouses": (cn, us), "skus": skus, "accounts": accounts}


def _sync_orders(company, actor):
    data = _foundation(company, actor)
    wave = timezone.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper()
    orders = []
    for index, account in enumerate(data["accounts"]):
        store = account.stores.first()
        sku = data["skus"][index % len(data["skus"])]
        amount = SKU_BLUEPRINTS[index]["price"]
        order = upsert_normalized_order(account, {
            "external_id": f"{account.provider[:3].upper()}-NEX-{wave}", "external_version": "1",
            "marketplace": store.marketplace, "status": Order.Status.PENDING, "fulfillment": SKU.Fulfillment.FBM,
            "ordered_at": (timezone.now() - timedelta(minutes=15 - index * 3)).isoformat(),
            "buyer_name": ["Olivia M.", "Noah W.", "Emma R."][index], "buyer_email": "masked@nexus.demo",
            "ship_to": {"country": "US", "state": ["CA", "TX", "WA"][index], "city": ["Irvine", "Austin", "Seattle"][index], "postal_code": "•••••"},
            "currency": "USD", "subtotal": str(amount), "shipping_income": "29.00", "tax": "0",
            "discount": "10.00", "total": str(amount + Decimal("19")),
            "items": [{"external_line_id": "1", "external_sku": sku.code, "title": sku.name, "quantity": "1", "unit_price": str(amount), "tax": "0", "discount": "10.00"}],
            "raw": {"simulated": True, "provider": account.provider, "wave": wave},
        })
        SyncJob.objects.create(
            account=account, job_type="orders", status="succeeded", started_at=timezone.now(),
            finished_at=timezone.now(), processed=1, cursor=wave,
            detail={"mode": "nexus-simulator", "order_id": str(order.id)},
        )
        account.last_sync_at = timezone.now()
        account.last_error = ""
        account.save(update_fields=["last_sync_at", "last_error", "updated_at"])
        orders.append(order)
    return {"created": len(orders), "wave": wave}


def _allocate(company, actor):
    rows = list(Order.objects.filter(company=company, status__in=[Order.Status.PENDING, Order.Status.ALLOCATING, Order.Status.BACKORDER]))
    completed = 0
    for order in rows:
        allocate_order(order, actor=actor)
        order.refresh_from_db()
        completed += int(order.status == Order.Status.PICKING)
    return {"processed": len(rows), "ready_to_pick": completed}


def _ship(company, actor):
    orders = list(Order.objects.filter(company=company, status=Order.Status.PICKING).prefetch_related("items__allocations"))
    shipped = 0
    for order in orders:
        warehouses = {allocation.warehouse for item in order.items.all() for allocation in item.allocations.all() if allocation.quantity > allocation.released_quantity}
        for warehouse in warehouses:
            shipment = Shipment.objects.create(
                company=company, order=order, warehouse=warehouse,
                shipment_no=f"SHP-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:5].upper()}", status=Shipment.Status.READY,
            )
            package = Package.objects.create(
                shipment=shipment, package_no="PKG-01", carrier="UPS", service="Ground",
                tracking_number=f"1ZNEX{uuid.uuid4().hex[:12].upper()}",
                weight_kg=sum((item.sku.gross_weight_kg * item.quantity for item in order.items.all()), Decimal("0")),
                dimensions={"unit": "cm", "multi_package": False},
            )
            for item in order.items.all():
                allocation = item.allocations.filter(warehouse=warehouse).first()
                if allocation and allocation.quantity > allocation.released_quantity:
                    ShipmentItem.objects.create(package=package, order_item=item, quantity=allocation.quantity - allocation.released_quantity)
            post_shipment(shipment, actor=actor)
            get_connector(order.store.account).push_tracking(shipment)
            shipment.external_status = "accepted"
            shipment.save(update_fields=["external_status", "updated_at"])
        base_total = order.total * RATE
        for kind, amount, note in (
            (FinanceEntry.Type.REVENUE, base_total, "销售收入"),
            (FinanceEntry.Type.COMMISSION, base_total * Decimal("0.15"), "平台佣金"),
            (FinanceEntry.Type.LAST_MILE, Decimal("188"), "尾程运费"),
        ):
            FinanceEntry.objects.get_or_create(
                company=company, external_id=f"nexus:{kind}:{order.id}",
                defaults={"entry_type": kind, "occurred_at": timezone.now(), "order": order, "currency": "CNY", "amount": amount, "exchange_rate": 1, "base_amount": amount, "note": f"NEXUS 模拟归集 · {note}"},
            )
        shipped += 1
    return {"shipped_orders": shipped, "tracking_pushed": shipped}


def _return_and_refund(company, actor):
    order = Order.objects.filter(
        company=company,
        status__in=[Order.Status.SHIPPED, Order.Status.PARTIALLY_SHIPPED],
        returns__isnull=True,
    ).prefetch_related("items").first()
    if not order:
        return {"processed": 0, "message": "没有等待售后的已发货订单"}
    item = order.items.first()
    shipment = order.shipments.first()
    return_order = ReturnOrder.objects.create(
        company=company, order=order, external_id=f"RET-NEX-{uuid.uuid4().hex[:10].upper()}",
        status=ReturnOrder.Status.RECEIVED, reason="模拟场景：尺寸不合适",
        return_shipping_cost=Decimal("86"), refund_amount=order.total, currency=order.currency,
        raw_payload={"simulated": True, "inspection": "restock"},
    )
    return_item = ReturnItem.objects.create(return_order=return_order, order_item=item, quantity=Decimal("1"))
    move_inventory(
        company=company, warehouse=shipment.warehouse, sku=item.sku,
        movement_type=InventoryLedger.Type.RETURN_RECEIPT, quantity_delta=return_item.quantity,
        unit_cost=item.sku.moving_average_cost, reference_type="return", reference_id=return_order.id,
        idempotency_key=f"nexus:return:{return_order.id}:{return_item.id}", note="退货质检：良品重新入库", actor=actor,
    )
    return_item.disposition, return_item.warehouse, return_item.inspected_at = "restock", shipment.warehouse, timezone.now()
    return_item.save(update_fields=["disposition", "warehouse", "inspected_at", "updated_at"])
    item.returned_quantity += return_item.quantity
    item.save(update_fields=["returned_quantity", "updated_at"])
    return_order.status = ReturnOrder.Status.REFUNDED
    return_order.save(update_fields=["status", "updated_at"])
    order.status = Order.Status.REFUNDED
    order.save(update_fields=["status", "updated_at"])
    refund = order.total * RATE
    for kind, amount, note in ((FinanceEntry.Type.REFUND, refund, "全额退款"), (FinanceEntry.Type.RETURN_LOSS, Decimal("86"), "退货物流损失")):
        FinanceEntry.objects.get_or_create(
            company=company, external_id=f"nexus:{kind}:{return_order.id}",
            defaults={"entry_type": kind, "occurred_at": timezone.now(), "order": order, "currency": "CNY", "amount": amount, "exchange_rate": 1, "base_amount": amount, "note": f"NEXUS 模拟售后 · {note}"},
        )
    return {"processed": 1, "return_id": str(return_order.id), "disposition": "restock"}


def _replenish(company, actor):
    _foundation(company, actor)
    rows = generate_for_company(company, window_days=30)
    if not rows:
        balance = InventoryBalance.objects.filter(company=company, warehouse__code="NEX-US-LA").select_related("sku").first()
        if balance:
            balance.sku.safety_stock = max(balance.sku.safety_stock, int(balance.available) + 24)
            balance.sku.save(update_fields=["safety_stock", "updated_at"])
            rows = generate_for_company(company, window_days=30)
    return {"suggestions": len(rows)}


def _approve_replenishment(company, actor):
    suggestions = list(ReplenishmentSuggestion.objects.filter(company=company, status=ReplenishmentSuggestion.Status.OPEN).select_related("sku__supplier", "warehouse"))
    created = 0
    for suggestion in suggestions:
        if not suggestion.sku.supplier:
            continue
        suggestion.adjusted_quantity = suggestion.suggested_quantity
        suggestion.adjustment_reason = "NEXUS 模拟审批：按整箱与 MOQ 执行"
        suggestion.approved_by, suggestion.approved_at = actor, timezone.now()
        suggestion.status = ReplenishmentSuggestion.Status.APPROVED
        suggestion.save()
        po = PurchaseOrder.objects.create(
            company=company, po_number=f"PO-NEX-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}",
            supplier=suggestion.sku.supplier, warehouse=suggestion.warehouse, status=PurchaseOrder.Status.ORDERED,
            currency=suggestion.sku.currency,
            expected_at=timezone.localdate() + timedelta(days=suggestion.sku.purchase_lead_days + suggestion.sku.production_lead_days + suggestion.sku.ocean_lead_days),
            approved_by=actor, approved_at=timezone.now(), notes="由 NEXUS 智能补货建议审批生成",
        )
        PurchaseOrderItem.objects.create(purchase_order=po, sku=suggestion.sku, quantity=suggestion.adjusted_quantity, unit_cost=suggestion.sku.purchase_price)
        suggestion.status = ReplenishmentSuggestion.Status.CONVERTED
        suggestion.save(update_fields=["status", "updated_at"])
        created += 1
    return {"purchase_orders": created}


def _receive(company, actor):
    purchase_orders = list(PurchaseOrder.objects.filter(
        company=company, status__in=[PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PRODUCTION, PurchaseOrder.Status.IN_TRANSIT, PurchaseOrder.Status.PARTIAL],
    ).prefetch_related("items"))
    receipts = 0
    for po in purchase_orders:
        remaining = [(item, item.quantity - item.received_quantity) for item in po.items.all() if item.quantity > item.received_quantity]
        if not remaining:
            continue
        po.status = PurchaseOrder.Status.IN_TRANSIT
        po.save(update_fields=["status", "updated_at"])
        receipt = Receipt.objects.create(
            company=company, receipt_no=f"RCV-NEX-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}",
            purchase_order=po, warehouse=po.warehouse, received_at=timezone.now(), allocation_method="volume",
            landed_cost=sum((quantity * item.unit_cost for item, quantity in remaining), Decimal("0")) * Decimal("0.12"),
        )
        for item, quantity in remaining:
            ReceiptItem.objects.create(receipt=receipt, purchase_order_item=item, quantity=quantity, unit_cost=item.unit_cost)
        post_receipt(receipt, actor=actor)
        receipts += 1
    return {"receipts": receipts, "cost_allocation": "volume"}


def _settle(company, actor):
    created = 0
    today = timezone.localdate()
    for account in ChannelAccount.objects.filter(company=company, is_enabled=True):
        orders = Order.objects.filter(company=company, store__account=account)
        gross = orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
        if gross <= 0:
            continue
        refunds = orders.filter(status=Order.Status.REFUNDED).aggregate(total=Sum("total"))["total"] or Decimal("0")
        fee = gross * Decimal("0.15")
        settlement, was_created = Settlement.objects.get_or_create(
            company=company, account=account, external_id=f"NEX-{today:%Y%m%d}",
            defaults={"period_start": today - timedelta(days=14), "period_end": today, "currency": "USD", "gross_amount": gross, "fee_amount": fee, "refund_amount": refunds, "net_amount": gross - fee - refunds, "status": "reconciled", "raw_payload": {"simulated": True, "matched_orders": orders.count()}},
        )
        FinanceEntry.objects.filter(company=company, order__store__account=account, settlement__isnull=True).update(settlement=settlement)
        FinanceEntry.objects.get_or_create(
            company=company, external_id=f"nexus:advertising:{settlement.id}",
            defaults={"entry_type": FinanceEntry.Type.ADVERTISING, "occurred_at": timezone.now(), "settlement": settlement, "currency": "CNY", "amount": gross * RATE * Decimal("0.04"), "exchange_rate": 1, "base_amount": gross * RATE * Decimal("0.04"), "note": "NEXUS 模拟结算 · 广告分摊"},
        )
        created += int(was_created)
    return {"settlements": created, "status": "reconciled"}


WORKFLOW_ACTIONS = {
    "bootstrap": lambda company, actor: {"skus": len(_foundation(company, actor)["skus"]), "channels": 3, "warehouses": 2},
    "sync_orders": _sync_orders,
    "allocate": _allocate,
    "ship": _ship,
    "return_refund": _return_and_refund,
    "replenish": _replenish,
    "approve_purchase": _approve_replenishment,
    "receive": _receive,
    "settle": _settle,
}


@transaction.atomic
def run_workflow_action(company, actor, action):
    handler = WORKFLOW_ACTIONS.get(action)
    if not handler:
        raise ValidationError(f"不支持的业务沙盘动作：{action}")
    return handler(company, actor)


def workflow_status(company):
    orders = Order.objects.filter(company=company)
    shipments = Shipment.objects.filter(company=company)
    finance = FinanceEntry.objects.filter(company=company)
    revenue = finance.filter(entry_type=FinanceEntry.Type.REVENUE).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
    cost_types = [kind for kind, _ in FinanceEntry.Type.choices if kind != FinanceEntry.Type.REVENUE]
    costs = finance.filter(entry_type__in=cost_types).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
    return {
        "mode": "simulator",
        "steps": [
            {"key": "bootstrap", "title": "演示账套", "description": "商品、三渠道、双仓与期初库存", "count": SKU.objects.filter(company=company, code__startswith="NEX-").count()},
            {"key": "sync_orders", "title": "订单同步", "description": "三平台统一订单与幂等归档", "count": orders.filter(raw_payload__simulated=True).count()},
            {"key": "allocate", "title": "智能分仓", "description": "按仓库优先级预占可用库存", "count": orders.filter(status__in=[Order.Status.PICKING, Order.Status.PARTIALLY_SHIPPED, Order.Status.SHIPPED, Order.Status.REFUNDED]).count()},
            {"key": "ship", "title": "拣货出库", "description": "库存扣减、多包裹与追踪回传", "count": shipments.filter(status=Shipment.Status.SHIPPED).count()},
            {"key": "return_refund", "title": "退货退款", "description": "质检、良品入库与利润重算", "count": ReturnOrder.objects.filter(company=company).count()},
            {"key": "replenish", "title": "智能补货", "description": "销量、提前期、安全库存与 MOQ", "count": ReplenishmentSuggestion.objects.filter(company=company).count()},
            {"key": "approve_purchase", "title": "采购审批", "description": "建议转单、审批与供应商履约", "count": PurchaseOrder.objects.filter(company=company, po_number__startswith="PO-NEX-").count()},
            {"key": "receive", "title": "到货入库", "description": "头程费用分摊与移动加权成本", "count": Receipt.objects.filter(company=company, receipt_no__startswith="RCV-NEX-").count()},
            {"key": "settle", "title": "结算利润", "description": "平台结算、费用匹配与贡献利润", "count": Settlement.objects.filter(company=company, external_id__startswith="NEX-").count()},
        ],
        "summary": {
            "orders": orders.count(), "pending_orders": orders.filter(status__in=[Order.Status.PENDING, Order.Status.BACKORDER]).count(),
            "shipments": shipments.filter(status=Shipment.Status.SHIPPED).count(), "returns": ReturnOrder.objects.filter(company=company).count(),
            "purchase_orders": PurchaseOrder.objects.filter(company=company).count(), "settlements": Settlement.objects.filter(company=company).count(),
            "revenue_cny": revenue, "profit_cny": revenue - costs,
        },
    }
