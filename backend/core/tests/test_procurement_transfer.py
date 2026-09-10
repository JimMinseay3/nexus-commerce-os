from decimal import Decimal

import pytest

from core.models import (
    InventoryBalance, PurchaseOrder, PurchaseOrderItem, Receipt, ReceiptItem, Transfer, TransferItem, Warehouse,
)
from core.services.inventory import move_inventory
from core.services.procurement import post_receipt
from core.services.transfers import receive_transfer, ship_transfer


@pytest.mark.django_db
def test_receipt_allocates_landed_cost(base_data):
    company, user, supplier, sku, warehouse = base_data
    po = PurchaseOrder.objects.create(company=company, po_number="PO-1", supplier=supplier, warehouse=warehouse, status="ordered")
    po_item = PurchaseOrderItem.objects.create(purchase_order=po, sku=sku, quantity=10, unit_cost=100)
    receipt = Receipt.objects.create(company=company, receipt_no="R-1", purchase_order=po, warehouse=warehouse, landed_cost=100, allocation_method="quantity")
    ReceiptItem.objects.create(receipt=receipt, purchase_order_item=po_item, quantity=10, unit_cost=100)
    post_receipt(receipt, actor=user)
    balance = InventoryBalance.objects.get(warehouse=warehouse, sku=sku)
    assert balance.on_hand == Decimal("10")
    assert balance.average_cost == Decimal("110")
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.COMPLETED


@pytest.mark.django_db
def test_transfer_moves_through_in_transit(base_data):
    company, user, _, sku, source = base_data
    destination = Warehouse.objects.create(company=company, code="W2", name="目标仓")
    move_inventory(company=company, warehouse=source, sku=sku, movement_type="opening", quantity_delta=10, unit_cost=100, idempotency_key="transfer-opening", actor=user)
    transfer = Transfer.objects.create(company=company, transfer_no="T-1", source=source, destination=destination)
    TransferItem.objects.create(transfer=transfer, sku=sku, quantity=4)
    ship_transfer(transfer, actor=user)
    assert InventoryBalance.objects.get(warehouse=source, sku=sku).on_hand == Decimal("6")
    assert InventoryBalance.objects.get(warehouse=destination, sku=sku).in_transit == Decimal("4")
    receive_transfer(transfer, actor=user)
    target = InventoryBalance.objects.get(warehouse=destination, sku=sku)
    assert target.on_hand == Decimal("4") and target.in_transit == Decimal("0")

