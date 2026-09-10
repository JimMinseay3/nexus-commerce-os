import hashlib
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .fields import EncryptedJSONField


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class Company(UUIDModel):
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=32, unique=True)
    base_currency = models.CharField(max_length=3, default="CNY")
    timezone = models.CharField(max_length=64, default="Asia/Shanghai")
    settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class UserProfile(UUIDModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        OPERATIONS = "operations", "运营"
        PROCUREMENT = "procurement", "采购"
        WAREHOUSE = "warehouse", "仓库"
        FINANCE = "finance", "财务"
        MANAGEMENT = "management", "管理层只读"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.OPERATIONS)
    phone = models.CharField(max_length=32, blank=True)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} / {self.get_role_display()}"


class AuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    company = models.ForeignKey(Company, null=True, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="audit_events")
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    action = models.CharField(max_length=80, db_index=True)
    resource_type = models.CharField(max_length=80, db_index=True)
    resource_id = models.CharField(max_length=80, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("审计日志不可修改")
        if not self.event_hash:
            raw = f"{self.previous_hash}|{self.created_at or timezone.now().isoformat()}|{self.action}|{self.resource_type}|{self.resource_id}|{secrets.token_hex(16)}"
            self.event_hash = hashlib.sha256(raw.encode()).hexdigest()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("审计日志不可删除")


class Brand(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="brands")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_brand_code")]


class Category(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_category_code")]


class Supplier(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="suppliers")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    currency = models.CharField(max_length=3, default="CNY")
    payment_terms_days = models.PositiveIntegerField(default=0)
    default_lead_time_days = models.PositiveIntegerField(default=30)
    performance_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_supplier_code")]

    def __str__(self):
        return self.name


class Product(UUIDModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "在售"
        PHASING_OUT = "phasing_out", "清退中"
        DISCONTINUED = "discontinued", "停产"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="products")
    spu = models.CharField(max_length=80)
    name = models.CharField(max_length=240)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "spu"], name="uniq_product_spu")]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self):
        return f"{self.spu} {self.name}"


class SKU(UUIDModel):
    class Fulfillment(models.TextChoices):
        FBM = "fbm", "FBM/自发货"
        FBA = "fba", "Amazon FBA"
        WFS = "wfs", "Walmart WFS"
        THIRD_PARTY = "3pl", "第三方仓"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="skus")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="skus")
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=240)
    barcode = models.CharField(max_length=80, blank=True)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="skus")
    supplier_sku = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=20, default="件")
    fulfillment = models.CharField(max_length=16, choices=Fulfillment.choices, default=Fulfillment.FBM)
    net_weight_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    gross_weight_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    length_cm = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    width_cm = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    height_cm = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    carton_count = models.PositiveIntegerField(default=1)
    carton_details = models.JSONField(default=list, blank=True)
    purchase_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    moving_average_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="CNY")
    moq = models.PositiveIntegerField(default=1)
    case_pack = models.PositiveIntegerField(default=1)
    safety_stock = models.PositiveIntegerField(default=0)
    purchase_lead_days = models.PositiveIntegerField(default=30)
    production_lead_days = models.PositiveIntegerField(default=0)
    ocean_lead_days = models.PositiveIntegerField(default=30)
    first_mile_mode = models.CharField(max_length=40, blank=True)
    tax_attributes = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_sku_code")]
        indexes = [models.Index(fields=["company", "is_active"]), models.Index(fields=["barcode"])]

    @property
    def volume_cbm(self):
        return (self.length_cm * self.width_cm * self.height_cm) / Decimal("1000000")

    def __str__(self):
        return self.code


class BOMComponent(UUIDModel):
    parent_sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="components")
    component_sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="used_in_boms")
    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["parent_sku", "component_sku"], name="uniq_bom_component")]


class ChannelAccount(UUIDModel):
    class Provider(models.TextChoices):
        AMAZON = "amazon", "Amazon"
        WAYFAIR = "wayfair", "Wayfair"
        WALMART = "walmart", "Walmart"
        MOCK = "mock", "本地模拟器"

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "沙箱"
        PRODUCTION = "production", "生产"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="channel_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    name = models.CharField(max_length=120)
    environment = models.CharField(max_length=16, choices=Environment.choices, default=Environment.SANDBOX)
    region = models.CharField(max_length=32, default="NA")
    credentials = EncryptedJSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    is_enabled = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "provider", "name"], name="uniq_channel_account")]

    def masked_credentials(self):
        return {key: ("••••" + str(value)[-4:] if value else "") for key, value in self.credentials.items()}

    def __str__(self):
        return f"{self.get_provider_display()} / {self.name}"


class Store(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stores")
    account = models.ForeignKey(ChannelAccount, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=120)
    external_id = models.CharField(max_length=120)
    marketplace = models.CharField(max_length=40)
    country = models.CharField(max_length=2, default="US")
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "external_id"], name="uniq_store_external")]


class ChannelSKU(UUIDModel):
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="channel_mappings")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="sku_mappings")
    external_sku = models.CharField(max_length=160)
    external_product_id = models.CharField(max_length=160, blank=True)
    fulfillment = models.CharField(max_length=16, choices=SKU.Fulfillment.choices, default=SKU.Fulfillment.FBM)
    inventory_buffer = models.PositiveIntegerField(default=0)
    max_sellable_quantity = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "external_sku"], name="uniq_channel_sku")]


class Warehouse(UUIDModel):
    class Type(models.TextChoices):
        DOMESTIC = "domestic", "国内仓"
        OVERSEAS = "overseas", "海外仓"
        PLATFORM = "platform", "平台仓"
        THIRD_PARTY = "3pl", "第三方仓"
        TRANSIT = "transit", "在途仓"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="warehouses")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.DOMESTIC)
    country = models.CharField(max_length=2, default="CN")
    owner = models.CharField(max_length=120, blank=True)
    fulfillment_node = models.CharField(max_length=120, blank=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_warehouse_code")]
        ordering = ["priority", "code"]

    def __str__(self):
        return self.name


class WarehouseBin(UUIDModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="bins")
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=120, blank=True)
    is_pickable = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["warehouse", "code"], name="uniq_warehouse_bin")]


class InventoryBalance(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="inventory_balances")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="inventory_balances")
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="inventory_balances")
    on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    reserved = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    in_transit = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    damaged = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    average_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["warehouse", "sku"], name="uniq_inventory_balance")]
        indexes = [models.Index(fields=["company", "warehouse"]), models.Index(fields=["company", "sku"])]

    @property
    def available(self):
        return self.on_hand - self.reserved - self.damaged


class InventoryLedger(models.Model):
    class Type(models.TextChoices):
        OPENING = "opening", "期初"
        PURCHASE_RECEIPT = "purchase_receipt", "采购入库"
        SALE_RESERVE = "sale_reserve", "销售预占"
        SALE_RELEASE = "sale_release", "释放预占"
        SALE_SHIP = "sale_ship", "销售出库"
        RETURN_RECEIPT = "return_receipt", "退货入库"
        TRANSFER_OUT = "transfer_out", "调拨出库"
        TRANSFER_IN = "transfer_in", "调拨入库"
        COUNT_ADJUST = "count_adjust", "盘点调整"
        DAMAGE = "damage", "残次/报废"
        EXTERNAL_SYNC = "external_sync", "外部同步"

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="inventory_ledger")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="inventory_ledger")
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="inventory_ledger")
    movement_type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    quantity_delta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    reserved_delta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    in_transit_delta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    damaged_delta = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=80, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    note = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["warehouse", "sku", "created_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("库存流水不可修改")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("库存流水不可删除")


class Order(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待确认"
        ALLOCATING = "allocating", "待分配"
        BACKORDER = "backorder", "缺货"
        PICKING = "picking", "待拣货"
        READY = "ready", "待发货"
        PARTIALLY_SHIPPED = "partially_shipped", "部分发货"
        SHIPPED = "shipped", "已发货"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"
        REFUNDED = "refunded", "已退款"
        CLOSED = "closed", "已关闭"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="orders")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="orders")
    external_id = models.CharField(max_length=160)
    external_version = models.CharField(max_length=80, default="1")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    fulfillment = models.CharField(max_length=16, choices=SKU.Fulfillment.choices, default=SKU.Fulfillment.FBM)
    ordered_at = models.DateTimeField(db_index=True)
    buyer_name = models.CharField(max_length=160, blank=True)
    buyer_email = models.CharField(max_length=254, blank=True)
    ship_to = models.JSONField(default=dict, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    shipping_income = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tax = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    discount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "external_id"], name="uniq_order_external")]
        indexes = [models.Index(fields=["company", "ordered_at"]), models.Index(fields=["store", "status"])]

    def __str__(self):
        return self.external_id


class OrderItem(UUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.ForeignKey(SKU, null=True, blank=True, on_delete=models.PROTECT, related_name="order_items")
    external_line_id = models.CharField(max_length=160)
    external_sku = models.CharField(max_length=160)
    title = models.CharField(max_length=300, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    shipped_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    returned_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tax = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    discount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "external_line_id"], name="uniq_order_line")]


class Allocation(UUIDModel):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="allocations")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="allocations")
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    released_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    status = models.CharField(max_length=20, default="reserved")


class Shipment(UUIDModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        READY = "ready", "待出库"
        SHIPPED = "shipped", "已发货"
        DELIVERED = "delivered", "已签收"
        FAILED = "failed", "回传失败"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="shipments")
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="shipments")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="shipments")
    shipment_no = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    shipped_at = models.DateTimeField(null=True, blank=True)
    external_status = models.CharField(max_length=80, blank=True)
    push_error = models.TextField(blank=True)


class Package(UUIDModel):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="packages")
    package_no = models.CharField(max_length=80)
    carrier = models.CharField(max_length=80)
    service = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=160)
    weight_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    dimensions = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shipment", "package_no"], name="uniq_shipment_package")]


class ShipmentItem(UUIDModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="shipment_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=4)


class ReturnOrder(UUIDModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "已申请"
        APPROVED = "approved", "已批准"
        IN_TRANSIT = "in_transit", "退回中"
        RECEIVED = "received", "已收货"
        INSPECTED = "inspected", "已质检"
        REFUNDED = "refunded", "已退款"
        CLOSED = "closed", "已关闭"
        REJECTED = "rejected", "已拒绝"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="returns")
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="returns")
    external_id = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField(max_length=240, blank=True)
    return_shipping_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="USD")
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "external_id"], condition=~models.Q(external_id=""), name="uniq_return_external")]


class ReturnItem(UUIDModel):
    return_order = models.ForeignKey(ReturnOrder, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="return_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    disposition = models.CharField(max_length=20, choices=[("restock", "良品入库"), ("damaged", "残次品"), ("discard", "报废")], blank=True)
    warehouse = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.PROTECT)
    inspected_at = models.DateTimeField(null=True, blank=True)


class PurchaseOrder(UUIDModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PENDING_APPROVAL = "pending_approval", "待审批"
        ORDERED = "ordered", "已下单"
        PRODUCTION = "production", "生产中"
        IN_TRANSIT = "in_transit", "在途"
        PARTIAL = "partial", "部分收货"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="purchase_orders")
    po_number = models.CharField(max_length=80, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3, default="CNY")
    expected_at = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_purchase_orders")
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    @property
    def total(self):
        return sum((item.quantity * item.unit_cost for item in self.items.all()), Decimal("0"))


class PurchaseOrderItem(UUIDModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="purchase_order_items")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["purchase_order", "sku"], name="uniq_po_sku")]


class Receipt(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="receipts")
    receipt_no = models.CharField(max_length=80, unique=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="receipts")
    received_at = models.DateTimeField(default=timezone.now)
    allocation_method = models.CharField(max_length=20, choices=[("quantity", "数量"), ("weight", "重量"), ("volume", "体积"), ("value", "货值")], default="quantity")
    landed_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    posted = models.BooleanField(default=False)


class ReceiptItem(UUIDModel):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    purchase_order_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, related_name="receipt_items")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    allocated_landed_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)


class Transfer(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="transfers")
    transfer_no = models.CharField(max_length=80, unique=True)
    source = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="outbound_transfers")
    destination = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="inbound_transfers")
    status = models.CharField(max_length=20, default="draft")


class TransferItem(UUIDModel):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="items")
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)


class StockCount(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="stock_counts")
    count_no = models.CharField(max_length=80, unique=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_counts")
    status = models.CharField(max_length=20, default="draft")
    counted_at = models.DateTimeField(null=True, blank=True)
    lines = models.JSONField(default=list, blank=True)


class ReplenishmentSuggestion(UUIDModel):
    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        APPROVED = "approved", "已批准"
        CONVERTED = "converted", "已转单"
        REJECTED = "rejected", "已拒绝"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="replenishment_suggestions")
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="replenishment_suggestions")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="replenishment_suggestions")
    store = models.ForeignKey(Store, null=True, blank=True, on_delete=models.CASCADE, related_name="replenishment_suggestions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    sales_window_days = models.PositiveIntegerField(default=30)
    daily_velocity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    season_factor = models.DecimalField(max_digits=8, decimal_places=4, default=1)
    suggested_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    adjusted_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    expected_stockout_at = models.DateField(null=True, blank=True)
    suggested_order_at = models.DateField(null=True, blank=True)
    explanation = models.JSONField(default=dict)
    adjustment_reason = models.CharField(max_length=500, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True, blank=True)


class ExchangeRate(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="exchange_rates")
    rate_date = models.DateField()
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3, default="CNY")
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    source = models.CharField(max_length=80, default="manual")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "rate_date", "from_currency", "to_currency"], name="uniq_exchange_rate")]


class Settlement(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="settlements")
    account = models.ForeignKey(ChannelAccount, on_delete=models.PROTECT, related_name="settlements")
    external_id = models.CharField(max_length=160)
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    net_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    status = models.CharField(max_length=20, default="open")
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "external_id"], name="uniq_settlement_external")]


class FinanceEntry(UUIDModel):
    class Type(models.TextChoices):
        REVENUE = "revenue", "销售收入"
        PRODUCT_COST = "product_cost", "商品成本"
        COMMISSION = "commission", "平台佣金"
        STORAGE = "storage", "仓储费"
        LAST_MILE = "last_mile", "尾程运费"
        FIRST_MILE = "first_mile", "头程运费"
        DUTY = "duty", "关税"
        VAT = "vat", "VAT/销售税"
        COUPON = "coupon", "优惠券"
        ADVERTISING = "advertising", "广告费"
        REFUND = "refund", "退款"
        RETURN_LOSS = "return_loss", "退货损失"
        OTHER = "other", "其他"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="finance_entries")
    entry_type = models.CharField(max_length=24, choices=Type.choices, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="finance_entries")
    settlement = models.ForeignKey(Settlement, null=True, blank=True, on_delete=models.PROTECT, related_name="entries")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    exchange_rate = models.DecimalField(max_digits=20, decimal_places=8, default=1)
    base_amount = models.DecimalField(max_digits=18, decimal_places=4)
    external_id = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=["company", "occurred_at"]), models.Index(fields=["order", "entry_type"])]
        constraints = [models.UniqueConstraint(fields=["company", "external_id"], condition=~models.Q(external_id=""), name="uniq_finance_external")]


class ImportTemplate(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="import_templates")
    name = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=40)
    mapping = models.JSONField(default=dict)


class ImportJob(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="import_jobs")
    resource_type = models.CharField(max_length=40)
    file = models.FileField(upload_to="imports/%Y/%m/%d/")
    mapping = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="uploaded")
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    preview = models.JSONField(default=list)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)


class ImportError(models.Model):
    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="errors")
    row_number = models.PositiveIntegerField()
    message = models.TextField()
    raw_data = models.JSONField(default=dict)


class SyncJob(UUIDModel):
    account = models.ForeignKey(ChannelAccount, on_delete=models.CASCADE, related_name="sync_jobs")
    job_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="queued", db_index=True)
    cursor = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    processed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    detail = models.JSONField(default=dict)


class IdempotencyRecord(models.Model):
    key = models.CharField(max_length=200, unique=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    request_hash = models.CharField(max_length=64)
    response_code = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class APIKey(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, company, name, scopes=None):
        raw = "erp_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(
            company=company,
            name=name,
            prefix=raw[:12],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scopes=scopes or [],
        )
        return obj, raw

    def verify(self, raw):
        return secrets.compare_digest(self.key_hash, hashlib.sha256(raw.encode()).hexdigest())


class WebhookSubscription(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="webhooks")
    name = models.CharField(max_length=120)
    url = models.URLField()
    secret = models.CharField(max_length=160)
    events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)


class Notification(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    level = models.CharField(max_length=16, default="info")
    title = models.CharField(max_length=160)
    message = models.TextField()
    resource_type = models.CharField(max_length=40, blank=True)
    resource_id = models.CharField(max_length=80, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
