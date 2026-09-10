import hashlib
import hmac
import json
from datetime import timedelta

import requests
from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .connectors import get_connector
from .models import ChannelAccount, Company, IntegrationConnection, OutboundAction, OutboxEvent, Shipment, WebhookSubscription
from .services.datahub import run_ingestion
from .services.outbound import execute_action
from .services.replenishment import generate_for_company
from .services.sync import sync_account


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def sync_channel_account(self, account_id, job_type="orders"):
    account = ChannelAccount.objects.get(pk=account_id)
    return str(sync_account(account, job_type=job_type).id)


@shared_task
def sync_enabled_accounts():
    count = 0
    for account in ChannelAccount.objects.filter(is_enabled=True):
        sync_channel_account.delay(str(account.id), "orders")
        count += 1
    return count


@shared_task
def sync_due_integrations():
    now = timezone.now()
    default_intervals = {"orders": 5, "inventory": 10, "catalog": 15, "procurement": 15, "transactions": 60, "settlements": 1440}
    capability_map = {"orders": "orders.read", "inventory": "inventory.read", "catalog": "catalog.read", "procurement": "procurement.read", "transactions": "finance.read", "settlements": "settlements.read"}
    dispatched = 0
    for item in IntegrationConnection.objects.filter(is_enabled=True).select_related("provider"):
        settings = dict(item.settings)
        configured = settings.get("resource_intervals", {})
        for resource, capability in capability_map.items():
            if capability not in item.enabled_capabilities:
                continue
            interval = int(configured.get(resource, default_intervals[resource]))
            marker = f"last_dispatched:{resource}"
            previous = parse_datetime(settings.get(marker, "")) if settings.get(marker) else None
            if previous and now - previous < timedelta(minutes=interval):
                continue
            sync_integration_connection.delay(str(item.id), resource)
            settings[marker] = now.isoformat()
            dispatched += 1
        item.settings = settings
        item.save(update_fields=["settings", "updated_at"])
    return dispatched


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def sync_integration_connection(self, connection_id, resource_type="orders", mode="incremental"):
    connection = IntegrationConnection.objects.get(pk=connection_id)
    run, result = run_ingestion(connection, resource_type=resource_type, mode=mode)
    return {"run_id": str(run.id), **result}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process_outbound_action(self, action_id):
    return execute_action(OutboundAction.objects.select_related("connection__provider").get(pk=action_id))


@shared_task
def publish_outbox_events():
    published = 0
    for event in OutboxEvent.objects.filter(status="pending").order_by("created_at")[:500]:
        deliver_webhook_event.delay(event.topic, event.payload, str(event.company_id))
        event.status, event.published_at, event.attempts = "published", timezone.now(), event.attempts + 1
        event.save(update_fields=["status", "published_at", "attempts", "updated_at"])
        published += 1
    return published


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def push_shipment_tracking(self, shipment_id):
    shipment = Shipment.objects.select_related("order__store__account").get(pk=shipment_id)
    result = get_connector(shipment.order.store.account).push_tracking(shipment)
    shipment.external_status = "accepted"
    shipment.push_error = ""
    shipment.save(update_fields=["external_status", "push_error", "updated_at"])
    deliver_webhook_event.delay("shipment.shipped", {
        "shipment_id": str(shipment.id), "shipment_no": shipment.shipment_no,
        "order_id": str(shipment.order.id), "external_order_id": shipment.order.external_id,
        "status": shipment.status,
    }, str(shipment.company_id))
    return result


@shared_task
def generate_replenishment_suggestions():
    return sum(len(generate_for_company(company)) for company in Company.objects.filter(is_active=True))


@shared_task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def deliver_webhook_event(self, event, payload, company_id):
    body = json.dumps({"event": event, "occurred_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "data": payload}, ensure_ascii=False, separators=(",", ":"))
    delivered = 0
    for hook in WebhookSubscription.objects.filter(company_id=company_id, is_active=True):
        if hook.events and event not in hook.events:
            continue
        signature = hmac.new(hook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        response = requests.post(hook.url, data=body.encode(), headers={"Content-Type": "application/json", "X-ERP-Event": event, "X-ERP-Signature": f"sha256={signature}"}, timeout=15)
        response.raise_for_status()
        delivered += 1
    return delivered
