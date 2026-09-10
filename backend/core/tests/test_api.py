import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_and_dashboard(base_data):
    _, user, _, _, _ = base_data
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": "tester", "password": "StrongPass123!"}, format="json")
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
    dashboard = client.get("/api/v1/reports/dashboard/")
    assert dashboard.status_code == 200
    assert "orders" in dashboard.data

