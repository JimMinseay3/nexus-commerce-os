from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from core.models import InventoryBalance, InventoryLedger
from core.services.inventory import move_inventory


@pytest.mark.django_db
def test_inventory_ledger_is_idempotent(base_data):
    company, user, _, sku, warehouse = base_data
    first, created = move_inventory(company=company, warehouse=warehouse, sku=sku, movement_type="opening", quantity_delta=10, unit_cost=100, idempotency_key="same", actor=user)
    second, created_again = move_inventory(company=company, warehouse=warehouse, sku=sku, movement_type="opening", quantity_delta=10, unit_cost=100, idempotency_key="same", actor=user)
    assert created is True and created_again is False and first.pk == second.pk
    assert InventoryBalance.objects.get(warehouse=warehouse, sku=sku).on_hand == Decimal("10")
    assert InventoryLedger.objects.count() == 1


@pytest.mark.django_db
def test_inventory_cannot_be_negative(base_data):
    company, user, _, sku, warehouse = base_data
    with pytest.raises(ValidationError):
        move_inventory(company=company, warehouse=warehouse, sku=sku, movement_type="sale_ship", quantity_delta=-1, idempotency_key="negative", actor=user)

