import pytest
from django.db import connection
from rest_framework.test import APIClient

from core.models import ChannelAccount, UserProfile


@pytest.mark.django_db
def test_channel_credentials_are_encrypted_at_rest(base_data):
    company, *_ = base_data
    account = ChannelAccount.objects.create(company=company, provider="amazon", name="secure", credentials={"client_secret": "never-store-plaintext"})
    with connection.cursor() as cursor:
        cursor.execute("SELECT credentials FROM core_channelaccount WHERE id = %s", [str(account.id)])
        row = cursor.fetchone()
        if row is None:  # SQLite stores UUID values without hyphens.
            cursor.execute("SELECT credentials FROM core_channelaccount WHERE id = %s", [account.id.hex])
            row = cursor.fetchone()
        stored = row[0]
    assert "never-store-plaintext" not in stored
    account.refresh_from_db()
    assert account.credentials["client_secret"] == "never-store-plaintext"


@pytest.mark.django_db
def test_management_role_is_read_only(base_data):
    company, user, *_ = base_data
    user.is_superuser = False
    user.save(update_fields=["is_superuser"])
    user.profile.role = UserProfile.Role.MANAGEMENT
    user.profile.save(update_fields=["role", "updated_at"])
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/suppliers/").status_code == 200
    assert client.post("/api/v1/suppliers/", {"code": "NO", "name": "无权限"}, format="json").status_code == 403
