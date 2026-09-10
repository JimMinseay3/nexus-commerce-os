import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    raw = settings.FIELD_ENCRYPTION_KEY or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


class EncryptedJSONField(models.TextField):
    """Encrypted-at-rest JSON. Never filter or order by this field."""

    description = "Encrypted JSON"

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return {}
        try:
            return json.loads(_fernet().decrypt(value.encode("utf-8")).decode("utf-8"))
        except (InvalidToken, ValueError, TypeError):
            return {}

    def to_python(self, value):
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}

    def get_prep_value(self, value):
        if value in (None, ""):
            value = {}
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return _fernet().encrypt(payload.encode("utf-8")).decode("utf-8")

