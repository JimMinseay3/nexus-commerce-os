import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models, serializers
from .audit import record_audit
from .connectors import get_connector
from .permissions import IsAdminRole, RolePermission
from .services.finance import COST_TYPES, order_profit
from .services.imports import RESOURCE_FIELDS, execute_import, preview_import
from .services.inventory import move_inventory
from .services.orders import allocate_order, post_shipment
from .services.procurement import post_receipt
from .services.replenishment import generate_for_company
from .services.transfers import receive_transfer, ship_transfer
from .tasks import push_shipment_tracking, sync_channel_account


def company_for(request):
    if hasattr(request.user, "company"):
        return request.user.company
    return getattr(getattr(request.user, "profile", None), "company", None)


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ok", "service": "cross-border-erp", "time": timezone.now()})


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer("LoginRequest", fields={"username": drf_serializers.CharField(), "password": drf_serializers.CharField()}),
        responses=OpenApiTypes.OBJECT,
        auth=[],
    )
    def post(self, request):
        username, password = request.data.get("username", ""), request.data.get("password", "")
        profile = models.UserProfile.objects.filter(user__username=username).select_related("user", "company").first()
        if profile and profile.locked_until and profile.locked_until > timezone.now():
            return Response({"detail": "账号暂时锁定，请稍后重试"}, status=status.HTTP_423_LOCKED)
        user = authenticate(request, username=username, password=password)
        if not user:
            if profile:
                profile.failed_login_count += 1
                if profile.failed_login_count >= 5:
                    profile.locked_until = timezone.now() + timedelta(minutes=30)
                    profile.failed_login_count = 0
                profile.save(update_fields=["failed_login_count", "locked_until", "updated_at"])
            return Response({"detail": "用户名或密码错误"}, status=status.HTTP_400_BAD_REQUEST)
        profile = user.profile
        profile.failed_login_count = 0
        profile.locked_until = None
        profile.save(update_fields=["failed_login_count", "locked_until", "updated_at"])
        token, _ = Token.objects.get_or_create(user=user)
        record_audit(request, "login", detail={"username": user.username}, company=profile.company)
        return Response({"token": token.key, "user": serializers.UserSerializer(user).data})


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        if isinstance(request.auth, Token):
            request.auth.delete()
        record_audit(request, "logout")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses=serializers.UserSerializer)
    def get(self, request):
        return Response(serializers.UserSerializer(request.user).data)


class AuditedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [RolePermission]

    def perform_create(self, serializer):
        kwargs = {}
        if hasattr(serializer.Meta.model, "company"):
            kwargs["company"] = company_for(self.request)
        instance = serializer.save(**kwargs)
        record_audit(self.request, "create", instance)

    def perform_update(self, serializer):
        before = {field.name: str(getattr(serializer.instance, field.name, "")) for field in serializer.instance._meta.fields if field.name not in {"credentials"}}
        instance = serializer.save()
        record_audit(self.request, "update", instance, {"before": before})

    def perform_destroy(self, instance):
        record_audit(self.request, "delete", instance)
        instance.delete()


class CompanyViewSet(AuditedModelViewSet):
    serializer_class = serializers.CompanySerializer
    permission_area = "admin"

    def get_queryset(self):
        company = company_for(self.request)
        return models.Company.objects.filter(pk=company.pk) if company else models.Company.objects.none()


class UserViewSet(AuditedModelViewSet):
    serializer_class = serializers.UserSerializer
    permission_classes = [IsAdminRole]
    permission_area = "admin"
    search_fields = ["username", "first_name", "last_name", "email"]

    def get_queryset(self):
        return User.objects.filter(profile__company=company_for(self.request)).select_related("profile")


class CompanyQuerySetMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        company = company_for(self.request)
        return queryset.filter(company=company).order_by("-created_at") if company else queryset.none()


class BrandViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Brand.objects.all()
    serializer_class = serializers.BrandSerializer
    permission_area = "products"
    search_fields = ["code", "name"]


class CategoryViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer
    permission_area = "products"
    search_fields = ["code", "name"]


class SupplierViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Supplier.objects.all()
    serializer_class = serializers.SupplierSerializer
    permission_area = "purchases"
    search_fields = ["code", "name", "contact_name"]
    filterset_fields = ["is_active", "currency"]


class ProductViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Product.objects.select_related("brand", "category")
    serializer_class = serializers.ProductSerializer
    permission_area = "products"
    search_fields = ["spu", "name"]
    filterset_fields = ["status", "brand", "category"]


class SKUViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.SKU.objects.select_related("product", "supplier")
    serializer_class = serializers.SKUSerializer
    permission_area = "products"
    search_fields = ["code", "name", "barcode", "supplier_sku"]
    filterset_fields = ["is_active", "fulfillment", "supplier", "product"]


class BOMViewSet(AuditedModelViewSet):
    queryset = models.BOMComponent.objects.select_related("parent_sku", "component_sku")
    serializer_class = serializers.BOMComponentSerializer
    permission_area = "products"

    def get_queryset(self):
        return super().get_queryset().filter(parent_sku__company=company_for(self.request))


class ChannelAccountViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ChannelAccount.objects.all()
    serializer_class = serializers.ChannelAccountSerializer
    permission_area = "integrations"
    filterset_fields = ["provider", "environment", "is_enabled"]
    search_fields = ["name"]

    @action(detail=True, methods=["post"])
    def test_connection(self, request, pk=None):
        account = self.get_object()
        result = get_connector(account).health()
        record_audit(request, "integration_test", account, {"ok": result["ok"]})
        return Response(result, status=status.HTTP_200_OK if result["ok"] else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def discover_capabilities(self, request, pk=None):
        account = self.get_object()
        account.capabilities = get_connector(account).discover_capabilities()
        account.save(update_fields=["capabilities", "updated_at"])
        record_audit(request, "discover_capabilities", account)
        return Response({"capabilities": account.capabilities})

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        account = self.get_object()
        job_type = request.data.get("job_type", "orders")
        result = sync_channel_account.delay(str(account.id), job_type)
        record_audit(request, "integration_sync", account, {"job_type": job_type})
        return Response({"task_id": result.id, "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def backfill(self, request, pk=None):
        account = self.get_object()
        settings = account.settings.copy()
        settings.pop("orders_cursor", None)
        settings["backfill_since"] = request.data.get("since")
        account.settings = settings
        account.save(update_fields=["settings", "updated_at"])
        result = sync_channel_account.delay(str(account.id), "orders")
        record_audit(request, "integration_backfill", account, {"since": request.data.get("since")})
        return Response({"task_id": result.id, "status": "queued"}, status=status.HTTP_202_ACCEPTED)


class StoreViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Store.objects.select_related("account")
    serializer_class = serializers.StoreSerializer
    permission_area = "integrations"
    search_fields = ["name", "external_id", "marketplace"]
    filterset_fields = ["account", "country", "is_active"]


class ChannelSKUViewSet(AuditedModelViewSet):
    queryset = models.ChannelSKU.objects.select_related("sku", "store")
    serializer_class = serializers.ChannelSKUSerializer
    permission_area = "products"
    search_fields = ["external_sku", "sku__code"]
    filterset_fields = ["store", "fulfillment", "is_active"]

    def get_queryset(self):
        return super().get_queryset().filter(sku__company=company_for(self.request))


class WarehouseViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Warehouse.objects.all()
    serializer_class = serializers.WarehouseSerializer
    permission_area = "warehouse"
    search_fields = ["code", "name", "fulfillment_node"]
    filterset_fields = ["type", "country", "is_active"]


class WarehouseBinViewSet(AuditedModelViewSet):
    queryset = models.WarehouseBin.objects.select_related("warehouse")
    serializer_class = serializers.WarehouseBinSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(warehouse__company=company_for(self.request))


class InventoryBalanceViewSet(CompanyQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = models.InventoryBalance.objects.select_related("sku", "warehouse")
    serializer_class = serializers.InventoryBalanceSerializer
    permission_classes = [RolePermission]
    permission_area = "warehouse"
    search_fields = ["sku__code", "sku__name", "warehouse__name"]
    filterset_fields = ["warehouse", "sku"]

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        company = company_for(request)
        warehouse = models.Warehouse.objects.get(pk=request.data["warehouse"], company=company)
        sku = models.SKU.objects.get(pk=request.data["sku"], company=company)
        idempotency_key = request.headers.get("X-Idempotency-Key") or request.data.get("idempotency_key")
        if not idempotency_key:
            return Response({"detail": "库存写入必须提供 X-Idempotency-Key"}, status=400)
        ledger, created = move_inventory(
            company=company, warehouse=warehouse, sku=sku,
            movement_type=request.data.get("movement_type", models.InventoryLedger.Type.COUNT_ADJUST),
            quantity_delta=request.data.get("quantity_delta", 0), reserved_delta=request.data.get("reserved_delta", 0),
            damaged_delta=request.data.get("damaged_delta", 0), unit_cost=request.data.get("unit_cost", 0),
            reference_type=request.data.get("reference_type", "api"), reference_id=request.data.get("reference_id", ""),
            idempotency_key=idempotency_key, note=request.data.get("note", ""),
            actor=request.user if getattr(request.user, "pk", None) else None,
        )
        record_audit(request, "inventory_adjust", ledger, {"created": created}, company=company)
        return Response(serializers.InventoryLedgerSerializer(ledger).data, status=201 if created else 200)


class InventoryLedgerViewSet(CompanyQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = models.InventoryLedger.objects.select_related("sku", "warehouse", "actor")
    serializer_class = serializers.InventoryLedgerSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["sku__code", "reference_id", "idempotency_key", "note"]
    filterset_fields = ["warehouse", "sku", "movement_type", "reference_type"]


class OrderViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Order.objects.select_related("store", "store__account").prefetch_related("items__sku")
    serializer_class = serializers.OrderSerializer
    permission_area = "orders"
    search_fields = ["external_id", "buyer_name", "items__external_sku"]
    filterset_fields = ["store", "status", "fulfillment", "currency"]
    ordering_fields = ["ordered_at", "total", "updated_at"]

    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        order = allocate_order(self.get_object(), actor=request.user)
        record_audit(request, "order_allocate", order)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["get"])
    def profit(self, request, pk=None):
        return Response(order_profit(self.get_object()))


class OrderItemViewSet(AuditedModelViewSet):
    queryset = models.OrderItem.objects.select_related("order", "sku")
    serializer_class = serializers.OrderItemSerializer
    permission_area = "orders"

    def get_queryset(self):
        return super().get_queryset().filter(order__company=company_for(self.request))


class AllocationViewSet(AuditedModelViewSet):
    queryset = models.Allocation.objects.select_related("order_item", "warehouse")
    serializer_class = serializers.AllocationSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(order_item__order__company=company_for(self.request))


class ShipmentViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Shipment.objects.select_related("order", "warehouse").prefetch_related("packages__items__order_item")
    serializer_class = serializers.ShipmentSerializer
    permission_area = "warehouse"
    search_fields = ["shipment_no", "order__external_id", "packages__tracking_number"]
    filterset_fields = ["status", "warehouse"]

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        shipment = post_shipment(self.get_object(), actor=request.user)
        task = push_shipment_tracking.delay(str(shipment.id))
        record_audit(request, "shipment_post", shipment)
        return Response({"shipment": self.get_serializer(shipment).data, "tracking_task_id": task.id})


class PackageViewSet(AuditedModelViewSet):
    queryset = models.Package.objects.select_related("shipment")
    serializer_class = serializers.PackageSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(shipment__company=company_for(self.request))


class ShipmentItemViewSet(AuditedModelViewSet):
    queryset = models.ShipmentItem.objects.select_related("package__shipment")
    serializer_class = serializers.ShipmentItemSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(package__shipment__company=company_for(self.request))


class ReturnOrderViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ReturnOrder.objects.select_related("order").prefetch_related("items")
    serializer_class = serializers.ReturnOrderSerializer
    permission_area = "orders"
    filterset_fields = ["status", "order"]
    search_fields = ["external_id", "order__external_id", "reason"]

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def inspect(self, request, pk=None):
        return_order = self.get_object()
        for item_data in request.data.get("items", []):
            item = return_order.items.select_related("order_item__sku").get(pk=item_data["id"])
            disposition = item_data["disposition"]
            warehouse = models.Warehouse.objects.get(pk=item_data["warehouse"], company=return_order.company)
            if disposition in {"restock", "damaged"}:
                move_inventory(
                    company=return_order.company, warehouse=warehouse, sku=item.order_item.sku,
                    movement_type=models.InventoryLedger.Type.RETURN_RECEIPT, quantity_delta=item.quantity,
                    damaged_delta=item.quantity if disposition == "damaged" else 0,
                    unit_cost=item.order_item.sku.moving_average_cost, reference_type="return", reference_id=return_order.id,
                    idempotency_key=f"return:{return_order.id}:{item.id}:{disposition}", actor=request.user,
                )
            item.disposition, item.warehouse, item.inspected_at = disposition, warehouse, timezone.now()
            item.save(update_fields=["disposition", "warehouse", "inspected_at", "updated_at"])
            item.order_item.returned_quantity += item.quantity
            item.order_item.save(update_fields=["returned_quantity", "updated_at"])
        return_order.status = models.ReturnOrder.Status.INSPECTED
        return_order.save(update_fields=["status", "updated_at"])
        record_audit(request, "return_inspect", return_order)
        return Response(self.get_serializer(return_order).data)


class ReturnItemViewSet(AuditedModelViewSet):
    queryset = models.ReturnItem.objects.select_related("return_order", "order_item")
    serializer_class = serializers.ReturnItemSerializer
    permission_area = "orders"

    def get_queryset(self):
        return super().get_queryset().filter(return_order__company=company_for(self.request))


class PurchaseOrderViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.PurchaseOrder.objects.select_related("supplier", "warehouse").prefetch_related("items__sku")
    serializer_class = serializers.PurchaseOrderSerializer
    permission_area = "purchases"
    search_fields = ["po_number", "supplier__name"]
    filterset_fields = ["status", "supplier", "warehouse", "currency"]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        po = self.get_object()
        po.status = models.PurchaseOrder.Status.PENDING_APPROVAL
        po.save(update_fields=["status", "updated_at"])
        record_audit(request, "purchase_submit", po)
        return Response(self.get_serializer(po).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        po = self.get_object()
        po.status, po.approved_by, po.approved_at = models.PurchaseOrder.Status.ORDERED, request.user, timezone.now()
        po.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        record_audit(request, "purchase_approve", po)
        return Response(self.get_serializer(po).data)


class PurchaseOrderItemViewSet(AuditedModelViewSet):
    queryset = models.PurchaseOrderItem.objects.select_related("purchase_order", "sku")
    serializer_class = serializers.PurchaseOrderItemSerializer
    permission_area = "purchases"

    def get_queryset(self):
        return super().get_queryset().filter(purchase_order__company=company_for(self.request))


class ReceiptViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Receipt.objects.select_related("purchase_order", "warehouse").prefetch_related("items")
    serializer_class = serializers.ReceiptSerializer
    permission_area = "warehouse"

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        receipt = post_receipt(self.get_object(), actor=request.user)
        record_audit(request, "receipt_post", receipt)
        return Response(self.get_serializer(receipt).data)


class ReceiptItemViewSet(AuditedModelViewSet):
    queryset = models.ReceiptItem.objects.select_related("receipt", "purchase_order_item")
    serializer_class = serializers.ReceiptItemSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(receipt__company=company_for(self.request))


class TransferViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Transfer.objects.select_related("source", "destination")
    serializer_class = serializers.TransferSerializer
    permission_area = "warehouse"

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        transfer = ship_transfer(self.get_object(), actor=request.user)
        record_audit(request, "transfer_ship", transfer)
        return Response(self.get_serializer(transfer).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        transfer = receive_transfer(self.get_object(), actor=request.user)
        record_audit(request, "transfer_receive", transfer)
        return Response(self.get_serializer(transfer).data)


class TransferItemViewSet(AuditedModelViewSet):
    queryset = models.TransferItem.objects.select_related("transfer", "sku")
    serializer_class = serializers.TransferItemSerializer
    permission_area = "warehouse"

    def get_queryset(self):
        return super().get_queryset().filter(transfer__company=company_for(self.request))


class StockCountViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.StockCount.objects.select_related("warehouse")
    serializer_class = serializers.StockCountSerializer
    permission_area = "warehouse"

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        count = self.get_object()
        for index, line in enumerate(count.lines):
            sku = models.SKU.objects.get(company=count.company, code=line["sku"])
            balance = models.InventoryBalance.objects.filter(warehouse=count.warehouse, sku=sku).first()
            current = balance.on_hand if balance else Decimal("0")
            delta = Decimal(str(line["counted_quantity"])) - current
            if delta:
                move_inventory(company=count.company, warehouse=count.warehouse, sku=sku,
                    movement_type=models.InventoryLedger.Type.COUNT_ADJUST, quantity_delta=delta,
                    reference_type="stock_count", reference_id=count.id,
                    idempotency_key=f"count:{count.id}:{index}", actor=request.user)
        count.status, count.counted_at = "approved", timezone.now()
        count.save(update_fields=["status", "counted_at", "updated_at"])
        record_audit(request, "stock_count_approve", count)
        return Response(self.get_serializer(count).data)


class ReplenishmentViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ReplenishmentSuggestion.objects.select_related("sku", "warehouse", "store")
    serializer_class = serializers.ReplenishmentSerializer
    permission_area = "purchases"
    filterset_fields = ["status", "warehouse", "sku", "store"]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        rows = generate_for_company(company_for(request), int(request.data.get("window_days", 30)))
        record_audit(request, "replenishment_generate", detail={"count": len(rows)})
        return Response(self.get_serializer(rows, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        suggestion = self.get_object()
        suggestion.adjusted_quantity = request.data.get("adjusted_quantity", suggestion.suggested_quantity)
        suggestion.adjustment_reason = request.data.get("adjustment_reason", "")
        suggestion.status, suggestion.approved_by, suggestion.approved_at = models.ReplenishmentSuggestion.Status.APPROVED, request.user, timezone.now()
        suggestion.save()
        record_audit(request, "replenishment_approve", suggestion)
        return Response(self.get_serializer(suggestion).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def convert(self, request, pk=None):
        suggestion = self.get_object()
        if suggestion.status != models.ReplenishmentSuggestion.Status.APPROVED:
            return Response({"detail": "请先审批补货建议"}, status=400)
        if not suggestion.sku.supplier:
            return Response({"detail": "SKU 未配置供应商"}, status=400)
        po = models.PurchaseOrder.objects.create(
            company=suggestion.company, po_number=f"PO-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(2).upper()}",
            supplier=suggestion.sku.supplier, warehouse=suggestion.warehouse, status=models.PurchaseOrder.Status.DRAFT,
            currency=suggestion.sku.currency,
        )
        models.PurchaseOrderItem.objects.create(purchase_order=po, sku=suggestion.sku, quantity=suggestion.adjusted_quantity or suggestion.suggested_quantity, unit_cost=suggestion.sku.purchase_price)
        suggestion.status = models.ReplenishmentSuggestion.Status.CONVERTED
        suggestion.save(update_fields=["status", "updated_at"])
        record_audit(request, "replenishment_convert", suggestion, {"purchase_order": str(po.id)})
        return Response(serializers.PurchaseOrderSerializer(po).data, status=201)


class ExchangeRateViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ExchangeRate.objects.all()
    serializer_class = serializers.ExchangeRateSerializer
    permission_area = "finance"
    filterset_fields = ["from_currency", "to_currency", "rate_date"]


class SettlementViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.Settlement.objects.select_related("account")
    serializer_class = serializers.SettlementSerializer
    permission_area = "finance"
    filterset_fields = ["account", "status", "currency"]
    search_fields = ["external_id"]


class FinanceEntryViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.FinanceEntry.objects.select_related("order", "settlement", "supplier")
    serializer_class = serializers.FinanceEntrySerializer
    permission_area = "finance"
    filterset_fields = ["entry_type", "currency", "order", "settlement", "supplier"]
    ordering_fields = ["occurred_at", "base_amount"]

    def perform_create(self, serializer):
        amount = serializer.validated_data["amount"]
        rate = serializer.validated_data.get("exchange_rate", Decimal("1"))
        instance = serializer.save(company=company_for(self.request), base_amount=amount * rate)
        record_audit(self.request, "finance_create", instance)


class ImportTemplateViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ImportTemplate.objects.all()
    serializer_class = serializers.ImportTemplateSerializer
    permission_area = "integrations"

    @action(detail=False, methods=["get"], url_path="download/(?P<resource_type>[^/.]+)")
    def download(self, request, resource_type=None):
        fields = RESOURCE_FIELDS.get(resource_type)
        if not fields:
            return Response({"detail": "不支持的模板类型"}, status=404)
        workbook, sheet = Workbook(), None
        sheet = workbook.active
        sheet.title = resource_type
        sheet.append(fields)
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{resource_type}.xlsx"'
        workbook.save(response)
        record_audit(request, "template_export", detail={"resource_type": resource_type})
        return response


class ImportJobViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.ImportJob.objects.prefetch_related("errors")
    serializer_class = serializers.ImportJobSerializer
    permission_area = "integrations"

    def perform_create(self, serializer):
        job = serializer.save(company=company_for(self.request), created_by=self.request.user)
        record_audit(self.request, "import_upload", job)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        job = self.get_object()
        result = preview_import(job)
        record_audit(request, "import_preview", job)
        return Response(result)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        job = execute_import(self.get_object(), actor=request.user)
        record_audit(request, "import_execute", job, {"success": job.success_rows, "errors": job.error_rows})
        return Response(self.get_serializer(job).data)


class SyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.SyncJob.objects.select_related("account")
    serializer_class = serializers.SyncJobSerializer
    filterset_fields = ["account", "job_type", "status"]

    def get_queryset(self):
        return super().get_queryset().filter(account__company=company_for(self.request))


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.AuditEvent.objects.select_related("actor")
    serializer_class = serializers.AuditEventSerializer
    filterset_fields = ["action", "resource_type", "actor"]
    search_fields = ["resource_id", "request_id"]

    def get_queryset(self):
        return super().get_queryset().filter(company=company_for(self.request))


class APIKeyViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.APIKey.objects.all()
    serializer_class = serializers.APIKeySerializer
    permission_area = "admin"

    def create(self, request, *args, **kwargs):
        key, raw = models.APIKey.issue(company_for(request), request.data["name"], request.data.get("scopes", ["read", "write"]))
        record_audit(request, "api_key_issue", key)
        return Response({**self.get_serializer(key).data, "key": raw}, status=201)


class WebhookViewSet(CompanyQuerySetMixin, AuditedModelViewSet):
    queryset = models.WebhookSubscription.objects.all()
    serializer_class = serializers.WebhookSerializer
    permission_area = "integrations"


class NotificationViewSet(CompanyQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = models.Notification.objects.all()
    serializer_class = serializers.NotificationSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self.request.user, "pk", None):
            queryset = queryset.filter(user__isnull=True) | queryset.filter(user=self.request.user)
        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])
        return Response(self.get_serializer(notification).data)


class DashboardView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        company = company_for(request)
        since = timezone.now() - timedelta(days=int(request.query_params.get("days", 30)))
        orders = models.Order.objects.filter(company=company, ordered_at__gte=since)
        entries = models.FinanceEntry.objects.filter(company=company, occurred_at__gte=since)
        revenue = entries.filter(entry_type=models.FinanceEntry.Type.REVENUE).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
        costs = entries.filter(entry_type__in=COST_TYPES).aggregate(v=Sum("base_amount"))["v"] or Decimal("0")
        inventory = models.InventoryBalance.objects.filter(company=company).aggregate(on_hand=Sum("on_hand"), reserved=Sum("reserved"), damaged=Sum("damaged"))
        low_stock = models.InventoryBalance.objects.filter(company=company, on_hand__lte=F("sku__safety_stock")).count()
        trend = list(orders.annotate(day=TruncDate("ordered_at")).values("day").annotate(orders=Count("id"), sales=Sum("total")).order_by("day"))
        return Response({
            "period_days": (timezone.now() - since).days, "orders": orders.count(),
            "sales": orders.aggregate(v=Sum("total"))["v"] or 0, "revenue_cny": revenue,
            "contribution_profit_cny": revenue - costs, "return_rate": self._return_rate(company, orders.count()),
            "inventory": inventory, "low_stock_skus": low_stock,
            "pending_purchase_approvals": models.PurchaseOrder.objects.filter(company=company, status=models.PurchaseOrder.Status.PENDING_APPROVAL).count(),
            "failed_sync_jobs": models.SyncJob.objects.filter(account__company=company, status="failed").count(),
            "trend": trend,
        })

    @staticmethod
    def _return_rate(company, order_count):
        return round(models.ReturnOrder.objects.filter(company=company).count() / order_count * 100, 2) if order_count else 0


class ProfitReportView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        company = company_for(request)
        rows = models.FinanceEntry.objects.filter(company=company).values("entry_type").annotate(amount=Sum("base_amount")).order_by("entry_type")
        return Response({"currency": company.base_currency, "rows": rows})
