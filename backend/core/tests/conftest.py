import pytest
from django.contrib.auth.models import User

from core.models import Company, Product, SKU, Supplier, Warehouse


@pytest.fixture
def base_data(db):
    company = Company.objects.create(code="T", name="测试公司")
    user = User.objects.create_user("tester", password="StrongPass123!", is_superuser=True)
    user.profile.company = company
    user.profile.save()
    supplier = Supplier.objects.create(company=company, code="S1", name="供应商")
    product = Product.objects.create(company=company, spu="P1", name="测试商品", status="active")
    sku = SKU.objects.create(company=company, product=product, supplier=supplier, code="SKU1", name="测试 SKU", purchase_price=100, moving_average_cost=100, safety_stock=5)
    warehouse = Warehouse.objects.create(company=company, code="W1", name="测试仓")
    return company, user, supplier, sku, warehouse

