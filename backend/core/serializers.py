from django.contrib.auth.models import User
from rest_framework import serializers

from . import models


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Company
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role", required=False)
    company_id = serializers.UUIDField(source="profile.company_id", read_only=True)
    password = serializers.CharField(write_only=True, required=False, min_length=10)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_active", "role", "company_id", "password", "last_login"]
        read_only_fields = ["last_login"]

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        user.profile.role = profile_data.get("role", models.UserProfile.Role.OPERATIONS)
        user.profile.company = self.context["request"].user.profile.company
        user.profile.save()
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        if "role" in profile_data:
            instance.profile.role = profile_data["role"]
            instance.profile.save(update_fields=["role", "updated_at"])
        return instance


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Brand
        fields = "__all__"
        read_only_fields = ["company"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Category
        fields = "__all__"
        read_only_fields = ["company"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Supplier
        fields = "__all__"
        read_only_fields = ["company"]


class ProductSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    sku_count = serializers.IntegerField(source="skus.count", read_only=True)

    class Meta:
        model = models.Product
        fields = "__all__"
        read_only_fields = ["company"]


class SKUSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    volume_cbm = serializers.DecimalField(max_digits=16, decimal_places=6, read_only=True)

    class Meta:
        model = models.SKU
        fields = "__all__"
        read_only_fields = ["company", "moving_average_cost"]


class BOMComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BOMComponent
        fields = "__all__"


class ChannelAccountSerializer(serializers.ModelSerializer):
    credentials = serializers.JSONField(write_only=True, required=False)
    masked_credentials = serializers.SerializerMethodField()
    provider_label = serializers.CharField(source="get_provider_display", read_only=True)

    class Meta:
        model = models.ChannelAccount
        fields = "__all__"
        read_only_fields = ["company", "capabilities", "last_sync_at", "last_error"]

    def get_masked_credentials(self, obj) -> dict:
        return obj.masked_credentials()

    def update(self, instance, validated_data):
        credentials = validated_data.pop("credentials", None)
        if credentials is not None:
            merged = instance.credentials.copy()
            merged.update({k: v for k, v in credentials.items() if v and not str(v).startswith("••••")})
            instance.credentials = merged
        return super().update(instance, validated_data)


class StoreSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="account.provider", read_only=True)

    class Meta:
        model = models.Store
        fields = "__all__"
        read_only_fields = ["company"]


class ChannelSKUSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = models.ChannelSKU
        fields = "__all__"


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Warehouse
        fields = "__all__"
        read_only_fields = ["company"]


class WarehouseBinSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.WarehouseBin
        fields = "__all__"


class InventoryBalanceSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)
    sku_name = serializers.CharField(source="sku.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    available = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = models.InventoryBalance
        fields = "__all__"
        read_only_fields = ["company", "on_hand", "reserved", "in_transit", "damaged", "average_cost"]


class InventoryLedgerSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = models.InventoryLedger
        fields = "__all__"


class OrderItemSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)

    class Meta:
        model = models.OrderItem
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    provider = serializers.CharField(source="store.account.provider", read_only=True)

    class Meta:
        model = models.Order
        fields = "__all__"
        read_only_fields = ["company", "raw_payload"]


class AllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Allocation
        fields = "__all__"


class ShipmentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ShipmentItem
        fields = "__all__"


class PackageSerializer(serializers.ModelSerializer):
    items = ShipmentItemSerializer(many=True, read_only=True)

    class Meta:
        model = models.Package
        fields = "__all__"


class ShipmentSerializer(serializers.ModelSerializer):
    packages = PackageSerializer(many=True, read_only=True)
    order_external_id = serializers.CharField(source="order.external_id", read_only=True)

    class Meta:
        model = models.Shipment
        fields = "__all__"
        read_only_fields = ["company", "shipped_at", "external_status", "push_error"]


class ReturnItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReturnItem
        fields = "__all__"


class ReturnOrderSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    order_external_id = serializers.CharField(source="order.external_id", read_only=True)

    class Meta:
        model = models.ReturnOrder
        fields = "__all__"
        read_only_fields = ["company", "raw_payload"]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)

    class Meta:
        model = models.PurchaseOrderItem
        fields = "__all__"


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = models.PurchaseOrder
        fields = "__all__"
        read_only_fields = ["company", "approved_by", "approved_at"]


class ReceiptItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReceiptItem
        fields = "__all__"


class ReceiptSerializer(serializers.ModelSerializer):
    items = ReceiptItemSerializer(many=True, read_only=True)

    class Meta:
        model = models.Receipt
        fields = "__all__"
        read_only_fields = ["company", "posted"]


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Transfer
        fields = "__all__"
        read_only_fields = ["company"]


class TransferItemSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)

    class Meta:
        model = models.TransferItem
        fields = "__all__"


class StockCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.StockCount
        fields = "__all__"
        read_only_fields = ["company"]


class ReplenishmentSerializer(serializers.ModelSerializer):
    sku_code = serializers.CharField(source="sku.code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = models.ReplenishmentSuggestion
        fields = "__all__"
        read_only_fields = ["company", "approved_by", "approved_at", "explanation"]


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ExchangeRate
        fields = "__all__"
        read_only_fields = ["company"]


class SettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Settlement
        fields = "__all__"
        read_only_fields = ["company", "raw_payload"]


class FinanceEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FinanceEntry
        fields = "__all__"
        read_only_fields = ["company", "base_amount"]


class ImportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ImportTemplate
        fields = "__all__"
        read_only_fields = ["company"]


class ImportErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ImportError
        fields = "__all__"


class ImportJobSerializer(serializers.ModelSerializer):
    errors = ImportErrorSerializer(many=True, read_only=True)

    class Meta:
        model = models.ImportJob
        fields = "__all__"
        read_only_fields = ["company", "status", "total_rows", "success_rows", "error_rows", "preview", "created_by"]


class SyncJobSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="account.provider", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = models.SyncJob
        fields = "__all__"


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = models.AuditEvent
        fields = "__all__"


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.APIKey
        fields = ["id", "name", "prefix", "scopes", "is_active", "last_used_at", "created_at"]
        read_only_fields = ["prefix", "last_used_at", "created_at"]


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.WebhookSubscription
        fields = "__all__"
        read_only_fields = ["company"]
        extra_kwargs = {"secret": {"write_only": True}}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Notification
        fields = "__all__"
        read_only_fields = ["company", "user"]
