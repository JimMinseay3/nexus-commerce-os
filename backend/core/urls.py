from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("companies", views.CompanyViewSet, basename="company")
router.register("users", views.UserViewSet, basename="user")
router.register("brands", views.BrandViewSet)
router.register("categories", views.CategoryViewSet)
router.register("suppliers", views.SupplierViewSet)
router.register("products", views.ProductViewSet)
router.register("skus", views.SKUViewSet)
router.register("bom-components", views.BOMViewSet)
router.register("channel-accounts", views.ChannelAccountViewSet)
router.register("stores", views.StoreViewSet)
router.register("sku-mappings", views.ChannelSKUViewSet)
router.register("warehouses", views.WarehouseViewSet)
router.register("warehouse-bins", views.WarehouseBinViewSet)
router.register("inventory-balances", views.InventoryBalanceViewSet)
router.register("inventory-ledger", views.InventoryLedgerViewSet)
router.register("orders", views.OrderViewSet)
router.register("order-items", views.OrderItemViewSet)
router.register("allocations", views.AllocationViewSet)
router.register("shipments", views.ShipmentViewSet)
router.register("packages", views.PackageViewSet)
router.register("shipment-items", views.ShipmentItemViewSet)
router.register("returns", views.ReturnOrderViewSet)
router.register("return-items", views.ReturnItemViewSet)
router.register("purchase-orders", views.PurchaseOrderViewSet)
router.register("purchase-order-items", views.PurchaseOrderItemViewSet)
router.register("receipts", views.ReceiptViewSet)
router.register("receipt-items", views.ReceiptItemViewSet)
router.register("transfers", views.TransferViewSet)
router.register("transfer-items", views.TransferItemViewSet)
router.register("stock-counts", views.StockCountViewSet)
router.register("replenishment-suggestions", views.ReplenishmentViewSet)
router.register("exchange-rates", views.ExchangeRateViewSet)
router.register("settlements", views.SettlementViewSet)
router.register("finance-entries", views.FinanceEntryViewSet)
router.register("import-templates", views.ImportTemplateViewSet)
router.register("imports", views.ImportJobViewSet)
router.register("sync-jobs", views.SyncJobViewSet)
router.register("audit-events", views.AuditEventViewSet)
router.register("api-keys", views.APIKeyViewSet)
router.register("webhooks", views.WebhookViewSet)
router.register("notifications", views.NotificationViewSet)
router.register("integration-providers", views.IntegrationProviderViewSet, basename="integration-provider")
router.register("integration-connections", views.IntegrationConnectionViewSet, basename="integration-connection")
router.register("field-definitions", views.FieldDefinitionViewSet, basename="field-definition")
router.register("mapping-sets", views.MappingSetViewSet, basename="mapping-set")
router.register("mapping-runs", views.MappingRunViewSet, basename="mapping-run")
router.register("ingestion-runs", views.IngestionRunViewSet, basename="ingestion-run")
router.register("raw-records", views.RawRecordViewSet, basename="raw-record")
router.register("data-conflicts", views.DataConflictViewSet, basename="data-conflict")
router.register("external-identities", views.ExternalIdentityViewSet, basename="external-identity")
router.register("outbound-actions", views.OutboundActionViewSet, basename="outbound-action")
router.register("analytics-saved-views", views.AnalyticsSavedViewViewSet, basename="analytics-saved-view")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("reports/dashboard/", views.DashboardView.as_view()),
    path("reports/profit/", views.ProfitReportView.as_view()),
    path("workflow-simulator/", views.WorkflowSimulationView.as_view()),
    path("lineage/<str:entity_type>/<uuid:entity_id>/", views.LineageView.as_view()),
    path("analytics/overview/", views.AnalyticsOverviewView.as_view()),
    path("analytics/workbench/", views.AnalyticsWorkbenchView.as_view()),
    path("analytics/export/", views.AnalyticsExportView.as_view()),
] + router.urls
