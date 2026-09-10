from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import ChannelAccount, ChannelSKU, InventoryBalance, Order, Store
from core.services.inventory import move_inventory
from core.services.orders import allocate_order
from core.services.sync import sync_account


@pytest.mark.django_db
def test_mock_sync_is_idempotent_and_allocates(base_data):
    company, user, _, sku, warehouse = base_data
    account = ChannelAccount.objects.create(company=company, provider="amazon", name="demo", environment="sandbox", settings={"use_mock": True, "marketplace": "US", "demo_sku": "SKU1"})
    store = Store.objects.create(company=company, account=account, name="demo", external_id="demo", marketplace="US", currency="USD")
    ChannelSKU.objects.create(store=store, sku=sku, external_sku="SKU1")
    move_inventory(company=company, warehouse=warehouse, sku=sku, movement_type="opening", quantity_delta=10, unit_cost=100, idempotency_key="opening", actor=user)
    sync_account(account)
    account.settings.pop("orders_cursor", None)
    account.save()
    sync_account(account)
    assert Order.objects.count() == 1
    order = Order.objects.first()
    allocate_order(order, actor=user)
    assert order.items.first().allocations.count() == 1
    balance = InventoryBalance.objects.get(warehouse=warehouse, sku=sku)
    assert balance.reserved == Decimal("1")

    inventory_job = sync_account(account, job_type="inventory")
    assert inventory_job.status == "succeeded"
    platform_balance = InventoryBalance.objects.get(warehouse__type="platform", sku=sku)
    assert platform_balance.on_hand == Decimal("18")
