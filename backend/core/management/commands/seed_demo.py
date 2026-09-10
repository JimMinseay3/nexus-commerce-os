from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    ChannelAccount, ChannelSKU, Company, FinanceEntry, Product, PurchaseOrder, PurchaseOrderItem,
    SKU, Store, Supplier, UserProfile, Warehouse,
)
from core.services.inventory import move_inventory
from core.services.sync import sync_account


class Command(BaseCommand):
    help = "创建可重复执行的完整演示账套"

    def handle(self, *args, **options):
        company, _ = Company.objects.get_or_create(code="DEMO", defaults={"name": "NEXUS 演示贸易有限公司"})
        admin, created = User.objects.get_or_create(username="admin", defaults={"first_name": "系统管理员", "email": "admin@example.invalid", "is_staff": True, "is_superuser": True})
        if created:
            admin.set_password("Admin123!")
            admin.save()
        admin.profile.company, admin.profile.role = company, UserProfile.Role.ADMIN
        admin.profile.save()

        supplier, _ = Supplier.objects.get_or_create(company=company, code="SUP-001", defaults={"name": "青岛木作工厂", "contact_name": "张经理", "currency": "CNY", "payment_terms_days": 30, "default_lead_time_days": 35})
        product, _ = Product.objects.get_or_create(company=company, spu="CHAIR-OAK", defaults={"name": "北欧橡木餐椅", "status": Product.Status.ACTIVE})
        sku, _ = SKU.objects.get_or_create(company=company, code="CHAIR-OAK-001", defaults={
            "product": product, "name": "北欧橡木餐椅·原木色", "supplier": supplier, "supplier_sku": "QD-C-1001",
            "purchase_price": Decimal("380"), "moving_average_cost": Decimal("380"), "gross_weight_kg": Decimal("12.5"),
            "length_cm": 82, "width_cm": 52, "height_cm": 47, "safety_stock": 15, "moq": 20, "case_pack": 2,
            "purchase_lead_days": 15, "production_lead_days": 20, "ocean_lead_days": 28, "first_mile_mode": "海运整柜",
        })
        cn, _ = Warehouse.objects.get_or_create(company=company, code="CN-SZ", defaults={"name": "深圳国内仓", "type": Warehouse.Type.DOMESTIC, "country": "CN", "priority": 20})
        us, _ = Warehouse.objects.get_or_create(company=company, code="US-LA", defaults={"name": "洛杉矶海外仓", "type": Warehouse.Type.OVERSEAS, "country": "US", "priority": 10})
        move_inventory(company=company, warehouse=cn, sku=sku, movement_type="opening", quantity_delta=80, unit_cost=380, reference_type="seed", reference_id="demo", idempotency_key="seed:opening:cn:chair", actor=admin)
        move_inventory(company=company, warehouse=us, sku=sku, movement_type="opening", quantity_delta=18, unit_cost=520, reference_type="seed", reference_id="demo", idempotency_key="seed:opening:us:chair", actor=admin)

        providers = [("amazon", "Amazon 美国站", "ATVPDKIKX0DER"), ("wayfair", "Wayfair Dropship", "US"), ("walmart", "Walmart US", "US")]
        for provider, name, marketplace in providers:
            account, _ = ChannelAccount.objects.get_or_create(company=company, provider=provider, name=name, defaults={"environment": "sandbox", "region": "NA", "settings": {"use_mock": True, "marketplace": marketplace, "demo_sku": sku.code}, "is_enabled": False})
            store, _ = Store.objects.get_or_create(company=company, account=account, external_id=f"{provider}-demo", defaults={"name": name, "marketplace": marketplace, "country": "US", "currency": "USD"})
            ChannelSKU.objects.get_or_create(sku=sku, store=store, external_sku=sku.code, defaults={"fulfillment": "fbm", "inventory_buffer": 3})
            try:
                sync_account(account)
            except Exception as exc:
                self.stderr.write(f"{provider} demo sync skipped: {exc}")

        order = company.orders.first()
        if order and not order.finance_entries.exists():
            for kind, amount in [(FinanceEntry.Type.REVENUE, "3081.60"), (FinanceEntry.Type.PRODUCT_COST, "520"), (FinanceEntry.Type.COMMISSION, "462.24"), (FinanceEntry.Type.LAST_MILE, "285")]:
                FinanceEntry.objects.create(company=company, entry_type=kind, occurred_at=order.ordered_at, order=order, currency="CNY", amount=Decimal(amount), exchange_rate=1, base_amount=Decimal(amount), note="演示数据")

        po, _ = PurchaseOrder.objects.get_or_create(company=company, po_number="PO-DEMO-001", defaults={"supplier": supplier, "warehouse": us, "status": PurchaseOrder.Status.PENDING_APPROVAL, "currency": "CNY", "expected_at": timezone.localdate() + timedelta(days=45), "notes": "演示采购单"})
        PurchaseOrderItem.objects.get_or_create(purchase_order=po, sku=sku, defaults={"quantity": 40, "unit_cost": 380})
        self.stdout.write(self.style.SUCCESS("演示账套已就绪：admin / Admin123!"))
