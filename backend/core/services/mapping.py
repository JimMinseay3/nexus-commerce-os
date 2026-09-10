from copy import deepcopy
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

from core.models import FieldDefinition, MappingRun, MappingVersion


ALLOWED_TRANSFORMS = {"string", "integer", "decimal", "boolean", "datetime", "date", "money", "quantity", "object", "array"}


def get_path(payload, path, default=None):
    if not path:
        return default
    value = payload
    for part in str(path).split("."):
        if isinstance(value, dict):
            value = value.get(part, default)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return default
    return value


def set_path(payload, path, value):
    target = payload
    parts = str(path).split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _boolean(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "是"}:
        return True
    if normalized in {"false", "0", "no", "n", "否"}:
        return False
    raise ValueError(f"无法转换为布尔值: {value}")


def convert_value(value, data_type, rule=None):
    rule = rule or {}
    if value is None or value == "":
        return rule.get("default")
    if rule.get("enum"):
        value = rule["enum"].get(str(value), rule.get("enum_default", value))
    factor = Decimal(str(rule.get("factor", 1)))
    try:
        if data_type == "string":
            value = str(value)
        elif data_type == "integer":
            value = int(Decimal(str(value)) * factor)
        elif data_type in {"decimal", "quantity"}:
            value = str(Decimal(str(value)) * factor)
        elif data_type == "money":
            if isinstance(value, dict):
                value = {"amount": str(Decimal(str(value.get("amount", 0))) * factor), "currency": value.get("currency") or rule.get("currency")}
            else:
                value = {"amount": str(Decimal(str(value)) * factor), "currency": rule.get("currency")}
        elif data_type == "boolean":
            value = _boolean(value)
        elif data_type == "datetime":
            parsed = value if isinstance(value, datetime) else parse_datetime(str(value))
            if not parsed:
                raise ValueError(f"无法解析日期时间: {value}")
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            value = parsed.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")
        elif data_type == "date":
            parsed = parse_date(str(value))
            if not parsed:
                raise ValueError(f"无法解析日期: {value}")
            value = parsed.isoformat()
        elif data_type == "array" and not isinstance(value, list):
            value = [value]
        elif data_type == "object" and not isinstance(value, dict):
            raise ValueError("目标字段要求对象")
        if rule.get("prefix"):
            value = f"{rule['prefix']}{value}"
        if rule.get("suffix"):
            value = f"{value}{rule['suffix']}"
        return value
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


def apply_mapping(payload, rules, company=None):
    output, errors = {}, []
    field_lookup = {
        row.key: row for row in FieldDefinition.objects.filter(is_current=True).filter(company__isnull=True)
    }
    if company:
        field_lookup.update({row.key: row for row in FieldDefinition.objects.filter(is_current=True, company=company)})
    for index, raw_rule in enumerate(rules):
        rule = deepcopy(raw_rule)
        target = rule.get("target")
        if not target:
            errors.append({"rule": index, "message": "缺少目标字段"})
            continue
        field = field_lookup.get(target)
        data_type = rule.get("type") or (field.data_type if field else "string")
        if data_type not in ALLOWED_TRANSFORMS:
            errors.append({"rule": index, "field": target, "message": f"不允许的转换类型: {data_type}"})
            continue
        sources = rule.get("sources") or ([rule.get("source")] if rule.get("source") else [])
        values = [get_path(payload, source) for source in sources]
        value = next((item for item in values if item not in (None, "")), rule.get("default"))
        if rule.get("concat"):
            value = str(rule.get("separator", "")).join(str(item) for item in values if item not in (None, ""))
        try:
            converted = convert_value(value, data_type, rule)
            if converted is None and (rule.get("required") or (field and field.required)):
                raise ValueError("必填字段为空")
            if field and field.enum_values and converted not in field.enum_values:
                raise ValueError(f"值不在标准枚举中: {converted}")
            set_path(output, target, converted)
        except ValueError as exc:
            errors.append({"rule": index, "field": target, "source": sources, "value": value, "message": str(exc)})
    return output, errors


def preview_mapping(mapping_version, samples, actor=None):
    outputs, errors = [], []
    for index, sample in enumerate(samples):
        output, row_errors = apply_mapping(sample, mapping_version.rules, mapping_version.mapping_set.company)
        outputs.append(output)
        errors.extend({"row": index + 1, **error} for error in row_errors)
    return MappingRun.objects.create(
        mapping_version=mapping_version, status="valid" if not errors else "invalid",
        input_count=len(samples), success_count=len(samples) - len({error["row"] for error in errors}),
        error_count=len({error["row"] for error in errors}), input_sample=samples[:20],
        output_sample=outputs[:20], errors=errors[:200], created_by=actor,
    )


def publish_mapping(mapping_version, actor=None):
    if mapping_version.status == "published":
        return mapping_version
    sample = [mapping_version.sample] if mapping_version.sample else []
    if sample:
        run = preview_mapping(mapping_version, sample, actor)
        if run.error_count:
            raise ValidationError({"detail": "映射样本校验失败", "errors": run.errors})
    MappingVersion.objects.filter(mapping_set=mapping_version.mapping_set, status="published").update(status="retired")
    mapping_version.status = "published"
    mapping_version.published_at = timezone.now()
    mapping_version.published_by = actor
    mapping_version.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    mapping_set = mapping_version.mapping_set
    mapping_set.status = "active"
    mapping_set.current_version = mapping_version.version
    mapping_set.save(update_fields=["status", "current_version", "updated_at"])
    return mapping_version
