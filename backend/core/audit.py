from .models import AuditEvent


def record_audit(request, action, instance=None, detail=None, company=None):
    actor = request.user if getattr(request.user, "pk", None) else None
    company = company or getattr(getattr(actor, "profile", None), "company", None)
    previous = AuditEvent.objects.order_by("-id").first()
    return AuditEvent.objects.create(
        company=company,
        actor=actor,
        request_id=getattr(request, "request_id", ""),
        action=action,
        resource_type=instance.__class__.__name__ if instance else "system",
        resource_id=str(getattr(instance, "pk", "")) if instance else "",
        ip_address=_client_ip(request),
        detail=detail or {},
        previous_hash=previous.event_hash if previous else "",
    )


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None

