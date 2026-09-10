from django.db import migrations


VIEW_SQL = {
    "dim_sku": """SELECT s.id, s.company_id, s.code AS sku_code, s.name AS sku_name, s.is_active, s.moving_average_cost, p.spu, p.name AS product_name FROM core_sku s JOIN core_product p ON p.id=s.product_id""",
    "dim_store": """SELECT s.id, s.company_id, s.name AS store_name, s.marketplace, s.country, s.currency, a.provider AS channel FROM core_store s JOIN core_channelaccount a ON a.id=s.account_id""",
    "dim_channel": """SELECT id, key AS channel_key, name AS channel_name, source_kind FROM core_integrationprovider""",
    "dim_warehouse": """SELECT id, company_id, code AS warehouse_code, name AS warehouse_name, type, country, owner, fulfillment_node FROM core_warehouse""",
    "dim_country": """SELECT DISTINCT country AS country_code FROM core_store UNION SELECT DISTINCT country AS country_code FROM core_warehouse""",
    "dim_date": """SELECT d::date AS date_key, EXTRACT(YEAR FROM d)::int AS year, EXTRACT(MONTH FROM d)::int AS month, EXTRACT(DAY FROM d)::int AS day, EXTRACT(ISODOW FROM d)::int AS iso_weekday FROM generate_series('2020-01-01'::date, '2035-12-31'::date, '1 day'::interval) d""",
    "fact_order_line": """SELECT i.id, o.company_id, o.id AS order_id, o.store_id, i.sku_id, o.ordered_at, o.status, o.currency, i.quantity, i.unit_price, i.tax, i.discount, (i.quantity*i.unit_price+i.tax-i.discount) AS line_amount FROM core_orderitem i JOIN core_order o ON o.id=i.order_id""",
    "fact_inventory_daily": """SELECT b.id, b.company_id, CURRENT_DATE AS snapshot_date, b.warehouse_id, b.sku_id, b.on_hand, b.reserved, (b.on_hand-b.reserved) AS available, b.in_transit, b.damaged, b.average_cost FROM core_inventorybalance b""",
    "fact_finance_entry": """SELECT id, company_id, order_id, settlement_id, entry_type, occurred_at, currency, amount, exchange_rate, base_amount FROM core_financeentry""",
    "fact_return": """SELECT id, company_id, order_id, external_id, status, currency, refund_amount, created_at FROM core_returnorder""",
    "fact_purchase_receipt": """SELECT ri.id, r.company_id, r.purchase_order_id, r.warehouse_id, r.received_at, poi.sku_id, ri.quantity, ri.unit_cost, ri.allocated_landed_cost FROM core_receiptitem ri JOIN core_receipt r ON r.id=ri.receipt_id JOIN core_purchaseorderitem poi ON poi.id=ri.purchase_order_item_id""",
}


def create_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name, query in VIEW_SQL.items():
            cursor.execute(f'CREATE OR REPLACE VIEW "{name}" AS {query}')


def drop_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name in reversed(list(VIEW_SQL)):
            cursor.execute(f'DROP VIEW IF EXISTS "{name}"')


class Migration(migrations.Migration):
    dependencies = [("core", "0005_seed_nexus_standard_catalog")]
    operations = [migrations.RunPython(create_views, drop_views)]
