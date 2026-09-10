import hashlib
import hmac
import json

import requests
from celery import shared_task

from .connectors import get_connector
from .models import ChannelAccount, Company, Shipment, WebhookSubscription
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
