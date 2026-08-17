from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from inventory.models import Supplier, Product

User = get_user_model()


class SupplierSearchAndAnnotationTests(TestCase):
    def setUp(self):
        # Create and authenticate a test user
        self.user = User.objects.create_user(
            username="testuser",
            password="password123"
        )
        self.client.login(username="testuser", password="password123")

        # Create suppliers
        self.supplier_a = Supplier.objects.create(name="Alpha Logistics", email="alpha@test.com")
        self.supplier_b = Supplier.objects.create(name="Beta Supplies", email="info@beta.com")
        self.supplier_c = Supplier.objects.create(name="Gamma Global", email="support@gamma.com")

        # Create products with unique SKUs and unit_prices
        Product.objects.create(
            sku="SKU-B1",
            name="Widget B1", 
            supplier=self.supplier_b, 
            stock_quantity=10, 
            reorder_level=5,
            unit_price=Decimal('19.99')
        )
        Product.objects.create(
            sku="SKU-C1",
            name="Widget C1", 
            supplier=self.supplier_c, 
            stock_quantity=10, 
            reorder_level=5,
            unit_price=Decimal('29.99')
        )
        Product.objects.create(
            sku="SKU-C2",
            name="Widget C2", 
            supplier=self.supplier_c, 
            stock_quantity=10, 
            reorder_level=5,
            unit_price=Decimal('39.99')
        )

        self.url = reverse('supplier_list')

    def test_empty_query_returns_all_suppliers(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['suppliers']), 3)

    def test_search_by_name(self):
        response = self.client.get(self.url, {'q': 'Alpha'})
        self.assertEqual(response.status_code, 200)
        suppliers = list(response.context['suppliers'])
        self.assertEqual(len(suppliers), 1)
        self.assertEqual(suppliers[0], self.supplier_a)

    def test_search_by_email(self):
        response = self.client.get(self.url, {'q': 'beta.com'})
        self.assertEqual(response.status_code, 200)
        suppliers = list(response.context['suppliers'])
        self.assertEqual(len(suppliers), 1)
        self.assertEqual(suppliers[0], self.supplier_b)

    def test_search_no_matches(self):
        response = self.client.get(self.url, {'q': 'NonExistent'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['suppliers']), 0)

    def test_product_count_annotation(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        suppliers_by_id = {s.id: s.product_count for s in response.context['suppliers']}
        
        self.assertEqual(suppliers_by_id[self.supplier_a.id], 0)
        self.assertEqual(suppliers_by_id[self.supplier_b.id], 1)
        self.assertEqual(suppliers_by_id[self.supplier_c.id], 2)