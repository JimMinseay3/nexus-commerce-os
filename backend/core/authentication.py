import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import APIKey


class APIKeyPrincipal:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, api_key):
        self.api_key = api_key
        self.company = api_key.company
        self.username = f"api:{api_key.name}"
        self.pk = None


class APIKeyAuthentication(BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request):
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return None
        prefix = raw[:12]
        try:
            key = APIKey.objects.select_related("company").get(prefix=prefix, is_active=True)
        except APIKey.DoesNotExist as exc:
            raise AuthenticationFailed("无效的 API Key") from exc
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if digest != key.key_hash:
            raise AuthenticationFailed("无效的 API Key")
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return APIKeyPrincipal(key), key
