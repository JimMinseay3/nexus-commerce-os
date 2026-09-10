from django.contrib import admin

from . import models


@admin.register(models.Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "base_currency", "is_active"]


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["spu", "name", "status", "company"]
    search_fields = ["spu", "name"]


@admin.register(models.SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "fulfillment", "is_active"]
    search_fields = ["code", "name", "barcode"]


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["external_id", "store", "status", "ordered_at", "total", "currency"]
    search_fields = ["external_id"]
    list_filter = ["status", "fulfillment"]


@admin.register(models.InventoryBalance)
class InventoryBalanceAdmin(admin.ModelAdmin):
    list_display = ["warehouse", "sku", "on_hand", "reserved", "damaged", "available"]
    search_fields = ["sku__code", "warehouse__name"]


@admin.register(models.ChannelAccount)
class ChannelAccountAdmin(admin.ModelAdmin):
    exclude = ["credentials"]
    list_display = ["provider", "name", "environment", "region", "is_enabled", "last_sync_at"]


for model in [models.Supplier, models.Warehouse, models.PurchaseOrder, models.Receipt, models.ReturnOrder,
              models.Settlement, models.FinanceEntry, models.ReplenishmentSuggestion, models.SyncJob,
              models.AuditEvent, models.ImportJob, models.APIKey, models.Notification]:
    admin.site.register(model)

admin.site.site_header = "NEXUS Commerce OS 管理后台"
admin.site.site_title = "ERP"
