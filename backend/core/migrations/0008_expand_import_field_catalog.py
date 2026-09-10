from django.db import migrations


FIELDS = [
    ("supplier.code", "supplier", "供应商编码", "Supplier code", "string"),
    ("supplier.name", "supplier", "供应商名称", "Supplier name", "string"),
    ("supplier.currency", "supplier", "供应商币种", "Supplier currency", "string"),
    ("product.spu", "catalog", "SPU", "SPU", "string"),
    ("product.name", "catalog", "商品名称", "Product name", "string"),
    ("sku.name", "catalog", "SKU 名称", "SKU name", "string"),
    ("sku.purchase_price", "catalog", "采购价", "Purchase price", "decimal"),
    ("channel_mapping.store_external_id", "catalog", "店铺外部 ID", "Store external ID", "string"),
    ("channel_mapping.internal_sku", "catalog", "内部 SKU", "Internal SKU", "string"),
    ("channel_mapping.external_sku", "catalog", "渠道 SKU", "External SKU", "string"),
    ("inventory.warehouse_code", "inventory", "仓库编码", "Warehouse code", "string"),
    ("inventory.sku", "inventory", "库存 SKU", "Inventory SKU", "string"),
    ("inventory.quantity", "inventory", "库存数量", "Inventory quantity", "quantity"),
    ("inventory.unit_cost", "inventory", "库存单位成本", "Inventory unit cost", "decimal"),
]


def seed(apps, schema_editor):
    Field = apps.get_model("core", "FieldDefinition")
    for key, domain, zh, en, data_type in FIELDS:
        Field.objects.get_or_create(key=key, version=1, defaults={"domain": domain, "name_zh": zh, "name_en": en, "data_type": data_type, "authority": "nexus", "is_current": True})


class Migration(migrations.Migration):
    dependencies = [("core", "0007_normalize_connection_capabilities")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
