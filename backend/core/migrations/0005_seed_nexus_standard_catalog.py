from django.db import migrations


PROVIDERS = [
    ("amazon", "Amazon", "sales_channel", ["orders.read", "returns.read", "inventory.read", "inventory.publish", "shipments.confirm", "tracking.push", "finance.read", "settlements.read"]),
    ("ebay", "eBay", "sales_channel", ["orders.read", "returns.read", "inventory.read", "inventory.publish", "tracking.push", "finance.read"]),
    ("walmart", "Walmart", "sales_channel", ["orders.read", "returns.read", "inventory.read", "inventory.publish", "shipments.confirm", "tracking.push", "finance.read", "settlements.read"]),
    ("wayfair", "Wayfair", "sales_channel", ["orders.read", "inventory.read", "inventory.publish", "shipments.confirm", "tracking.push"]),
    ("lingxing", "领星 ERP", "erp", ["catalog.read", "orders.read", "inventory.read", "procurement.read", "finance.read", "settlements.read"]),
    ("file", "Excel / CSV", "file", ["catalog.read", "orders.read", "inventory.read", "procurement.read", "finance.read"]),
]

FIELDS = [
    ("order.channel_order_id", "order", "渠道订单号", "Channel order ID", "string", "sales_channel", True, False),
    ("order.ordered_at", "order", "下单时间", "Ordered at", "datetime", "sales_channel", True, False),
    ("order.status", "order", "标准订单状态", "Canonical status", "string", "nexus", True, False),
    ("order.source_status", "order", "来源订单状态", "Source status", "string", "sales_channel", True, False),
    ("order.currency", "order", "原币币种", "Source currency", "string", "sales_channel", True, True),
    ("order.total", "order", "订单总额", "Order total", "money", "sales_channel", True, True),
    ("order.items", "order", "订单明细", "Order items", "array", "sales_channel", False, False),
    ("sku.code", "catalog", "内部 SKU", "Internal SKU", "string", "nexus", True, False),
    ("sku.channel_sku", "catalog", "渠道 SKU", "Channel SKU", "string", "sales_channel", True, False),
    ("inventory.on_hand_quantity", "inventory", "现有量", "On-hand quantity", "quantity", "nexus", True, True),
    ("inventory.reserved_quantity", "inventory", "预占量", "Reserved quantity", "quantity", "nexus", True, True),
    ("inventory.available_quantity", "inventory", "可用量", "Available quantity", "quantity", "nexus", True, True),
    ("inventory.node", "inventory", "履约节点", "Fulfillment node", "string", "nexus", True, False),
    ("inventory.owner", "inventory", "库存所有权", "Inventory owner", "string", "nexus", True, False),
    ("shipment.tracking_number", "shipment", "追踪号", "Tracking number", "string", "nexus", True, False),
    ("finance.amount", "finance", "原币金额", "Source amount", "money", "sales_channel", True, True),
    ("finance.base_amount", "finance", "本位币金额", "Base amount", "money", "nexus", True, True),
]

METRICS = [
    ("gmv", "GMV", "Gross merchandise value", "CNY"),
    ("net_sales", "净销售额", "Net sales", "CNY"),
    ("refund_rate", "退货率", "Refund rate", "%"),
    ("contribution_profit", "贡献利润", "Contribution profit", "CNY"),
    ("inventory_available", "可用库存", "Available inventory", "件"),
    ("stockout_rate", "缺货率", "Stockout rate", "%"),
]


def seed_catalog(apps, schema_editor):
    Provider = apps.get_model("core", "IntegrationProvider")
    Connection = apps.get_model("core", "IntegrationConnection")
    ChannelAccount = apps.get_model("core", "ChannelAccount")
    Field = apps.get_model("core", "FieldDefinition")
    Metric = apps.get_model("core", "MetricDefinition")
    providers = {}
    for key, name, kind, capabilities in PROVIDERS:
        providers[key], _ = Provider.objects.update_or_create(
            key=key, defaults={"name": name, "source_kind": kind, "capabilities": capabilities, "is_active": True}
        )
    for account in ChannelAccount.objects.all().iterator():
        provider = providers.get(account.provider)
        if provider:
            Connection.objects.get_or_create(
                legacy_account=account,
                defaults={
                    "company": account.company, "provider": provider, "name": account.name,
                    "environment": account.environment, "region": account.region,
                    "credentials": account.credentials, "settings": account.settings,
                    "enabled_capabilities": provider.capabilities, "is_enabled": account.is_enabled,
                    "last_sync_at": account.last_sync_at, "last_error": account.last_error,
                },
            )
    for key, domain, zh, en, data_type, authority, filterable, aggregatable in FIELDS:
        Field.objects.get_or_create(
            key=key, version=1,
            defaults={"domain": domain, "name_zh": zh, "name_en": en, "data_type": data_type,
                      "authority": authority, "is_filterable": filterable, "is_aggregatable": aggregatable,
                      "is_current": True},
        )
    for key, zh, en, unit in METRICS:
        Metric.objects.get_or_create(key=key, defaults={"name_zh": zh, "name_en": en, "unit": unit, "version": 1})


class Migration(migrations.Migration):
    dependencies = [("core", "0004_integrationprovider_metricdefinition_and_more")]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
