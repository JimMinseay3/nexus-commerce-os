from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.models import (
    ChannelAccount, DataConflict, ExternalIdentity, IntegrationConnection, IntegrationProvider,
    ImportJob, MappingSet, MappingVersion, Order, RawRecord, Store, Supplier,
)
from core.services.datahub import ingest_records, replay_raw_record
from core.services.mapping import preview_mapping, publish_mapping
from core.services.outbound import queue_action
from core.services.imports import execute_import, preview_import


def connection(company, key, name):
    provider = IntegrationProvider.objects.get(key=key)
    account = ChannelAccount.objects.create(company=company, provider=key, name=name, environment="sandbox", settings={"use_mock": True})
    Store.objects.create(company=company, account=account, external_id=f"{key}-us", name=name, marketplace="US", country="US", currency="USD")
    return IntegrationConnection.objects.create(company=company, provider=provider, legacy_account=account, name=name, environment="sandbox", settings={"use_mock": True})


def normalized_order(external_id="AMZ-1001"):
    return {
        "external_id": external_id, "external_version": "1", "marketplace": "US", "status": "pending",
        "source_status": "Unshipped", "source_timezone": "UTC", "fulfillment": "fbm",
        "ordered_at": (timezone.now() - timedelta(hours=1)).isoformat(), "currency": "USD",
        "subtotal": "100", "shipping_income": "0", "tax": "0", "discount": "0", "total": "100",
        "items": [{"external_line_id": "1", "external_sku": "SKU1", "title": "Chair", "quantity": 1, "unit_price": "100"}],
    }


@pytest.mark.django_db
def test_amazon_and_lingxing_resolve_to_one_order(base_data):
    company, *_ = base_data
    amazon = connection(company, "amazon", "Amazon direct")
    lingxing = connection(company, "lingxing", "Lingxing reference")
    assert ingest_records(amazon, "orders", [normalized_order()])["merged"] == 1
    second = normalized_order()
    second["extensions"] = {"lingxing": {"sid": "store-88"}}
    second["total"] = "99"
    assert ingest_records(lingxing, "orders", [second])["merged"] == 1
    assert Order.objects.filter(company=company).count() == 1
    assert RawRecord.objects.filter(company=company).count() == 2
    assert ExternalIdentity.objects.filter(company=company, object_type="order").count() == 2
    assert Order.objects.get().extensions["lingxing"]["sid"] == "store-88"
    assert Order.objects.get().total == 100
    assert DataConflict.objects.filter(field_key="order.total", status="open").count() == 1


@pytest.mark.django_db
def test_raw_event_is_idempotent_across_runs(base_data):
    company, *_ = base_data
    amazon = connection(company, "amazon", "Amazon replay")
    payload = normalized_order("AMZ-REPLAY")
    first = ingest_records(amazon, "orders", [payload])
    second = ingest_records(amazon, "orders", [payload])
    assert first["merged"] == 1
    assert second["duplicate"] == 1
    assert Order.objects.filter(company=company, external_id="AMZ-REPLAY").count() == 1


@pytest.mark.django_db
def test_mapping_preview_publish_and_raw_replay(base_data):
    company, user, *_ = base_data
    ebay = connection(company, "ebay", "eBay mapping")
    mapping_set = MappingSet.objects.create(company=company, connection=ebay, name="eBay order v1", resource_type="orders")
    version = MappingVersion.objects.create(mapping_set=mapping_set, version=1, sample={"id": "EB-1", "when": timezone.now().isoformat(), "value": "39.90"}, rules=[
        {"source": "id", "target": "order.channel_order_id", "type": "string"},
        {"source": "when", "target": "order.ordered_at", "type": "datetime"},
        {"source": "value", "target": "order.total", "type": "money", "currency": "USD"},
    ])
    preview = preview_mapping(version, [version.sample], user)
    assert preview.error_count == 0
    assert preview.output_sample[0]["order"]["total"] == {"amount": "39.90", "currency": "USD"}
    publish_mapping(version, user)
    version.rules = []
    with pytest.raises(ValidationError):
        version.save()
    result = ingest_records(ebay, "orders", [version.sample], mapping_version=MappingVersion.objects.get(pk=version.pk))
    assert result["merged"] == 1
    raw = RawRecord.objects.get(external_id="EB-1")
    assert replay_raw_record(raw)["merged"] == 1


@pytest.mark.django_db
def test_lingxing_writeback_is_not_whitelisted(base_data):
    company, *_ = base_data
    lingxing = connection(company, "lingxing", "Lingxing read only")
    with pytest.raises(ValueError, match="未声明写回能力"):
        queue_action(lingxing, "inventory.publish", {"items": []}, "lx:no-write")


@pytest.mark.django_db
def test_datahub_api_catalog_and_lineage(base_data):
    company, user, *_ = base_data
    amazon = connection(company, "amazon", "Amazon API")
    ingest_records(amazon, "orders", [normalized_order("AMZ-API")])
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/integration-providers/").status_code == 200
    assert client.get("/api/v1/field-definitions/").status_code == 200
    analytics = client.get("/api/v1/analytics/overview/")
    assert analytics.status_code == 200
    order = Order.objects.get(external_id="AMZ-API")
    lineage = client.get(f"/api/v1/lineage/order/{order.id}/")
    assert lineage.status_code == 200
    assert len(lineage.data["sources"]) == 1

    ebay_provider = IntegrationProvider.objects.get(key="ebay")
    created = client.post("/api/v1/integration-connections/", {
        "provider": str(ebay_provider.id), "name": "eBay API connection", "environment": "sandbox",
        "region": "NA", "credentials": {}, "settings": {"use_mock": True}, "is_enabled": True,
    }, format="json")
    assert created.status_code == 201, created.data
    new_connection = IntegrationConnection.objects.get(pk=created.data["id"])
    assert new_connection.legacy_account.provider == "ebay"
    assert "orders.read" in new_connection.enabled_capabilities


@pytest.mark.django_db
def test_csv_import_uses_published_mapping_and_archives_raw(base_data, tmp_path):
    company, user, *_ = base_data
    mapping_set = MappingSet.objects.create(company=company, name="供应商 CSV", resource_type="suppliers")
    version = MappingVersion.objects.create(mapping_set=mapping_set, version=1, rules=[
        {"source": "vendor_code", "target": "supplier.code", "type": "string"},
        {"source": "vendor_name", "target": "supplier.name", "type": "string"},
        {"source": "money", "target": "supplier.currency", "type": "string"},
    ], sample={"vendor_code": "S2", "vendor_name": "新供应商", "money": "CNY"})
    publish_mapping(version, user)
    upload = SimpleUploadedFile("vendors.csv", "vendor_code,vendor_name,money\nS2,新供应商,CNY\n".encode("utf-8-sig"), content_type="text/csv")
    with override_settings(MEDIA_ROOT=tmp_path):
        job = ImportJob.objects.create(company=company, resource_type="suppliers", file=upload, mapping={"mapping_version_id": str(version.id)}, created_by=user)
        preview = preview_import(job)
        assert preview["rows"][0]["code"] == "S2"
        execute_import(job, user)
    assert Supplier.objects.filter(company=company, code="S2", name="新供应商").exists()
    assert RawRecord.objects.filter(company=company, object_type="suppliers", mapping_version=version).count() == 1
