import pytest
from rest_framework.test import APIClient

from core.models import FinanceEntry, InventoryLedger, Order, Receipt, Settlement, Shipment


@pytest.mark.django_db(transaction=True)
def test_nexus_simulator_runs_complete_business_chain(base_data):
    company, user, *_ = base_data
    client = APIClient()
    client.force_authenticate(user)

    actions = [
        "bootstrap",
        "sync_orders",
        "allocate",
        "ship",
        "return_refund",
        "replenish",
        "approve_purchase",
        "receive",
        "settle",
    ]
    for action in actions:
        response = client.post("/api/v1/workflow-simulator/", {"action": action}, format="json")
        assert response.status_code == 200, (action, response.data)

    status = client.get("/api/v1/workflow-simulator/")
    assert status.status_code == 200
    assert status.data["mode"] == "simulator"
    assert len(status.data["steps"]) == 9
    assert Order.objects.filter(company=company).count() == 3
    assert Order.objects.filter(company=company, status__in=["shipped", "refunded"]).count() == 3
    assert Shipment.objects.filter(company=company, status="shipped").count() == 3
    assert Receipt.objects.filter(company=company, posted=True).exists()
    assert Settlement.objects.filter(company=company, status="reconciled").count() == 3
    assert FinanceEntry.objects.filter(company=company, entry_type="revenue").count() == 3
    assert InventoryLedger.objects.filter(company=company, movement_type="sale_ship").count() == 3


@pytest.mark.django_db
def test_nexus_simulator_rejects_unknown_action(base_data):
    _, user, *_ = base_data
    client = APIClient()
    client.force_authenticate(user)
    response = client.post("/api/v1/workflow-simulator/", {"action": "launch_rocket"}, format="json")
    assert response.status_code == 400
