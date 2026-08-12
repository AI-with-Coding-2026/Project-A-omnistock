from django.test import TestCase
from django.contrib.auth import get_user_model
from inventory.models import Product, Supplier

User = get_user_model()

class ProductModelTest(TestCase):
    def setUp(self):

        self.supplier = Supplier.objects.create(name="Test Supplier", email="test@supp.com")

    def test_auto_generate_sku(self):

        product = Product.objects.create(
            supplier=self.supplier,
            name="Test Product",
            unit_price=10.00,
            stock_quantity=5,
            reorder_level=2
        )

        self.assertIsNotNone(product.sku)

        self.assertTrue(product.sku.startswith("SUP-PROD-"))

    def test_admin_access_create_view(self):

        admin_user = User.objects.create_superuser(username="admin_test", password="password", role="ADMIN")
        self.client.login(username="admin_test", password="password")
        
        response = self.client.get('/inventory/products/create/')
        self.assertEqual(response.status_code, 200)