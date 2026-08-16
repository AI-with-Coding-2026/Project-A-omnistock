from django.test import TestCase
from django.urls import reverse

from core.models import User
from inventory.models import Product, Supplier


class ProductIndexViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_test', password='TestPass123!'
        )
        self.staff_user.role = 'STAFF'
        self.staff_user.save()
        self.client.force_login(self.staff_user)

        self.supplier_a = Supplier.objects.create(name='Acme Supplies', email='acme@example.com')
        self.supplier_b = Supplier.objects.create(name='Widget Co', email='widgetco@example.com')

        self.widget_a = Product.objects.create(
            sku='WD-1001', name='Widget A', supplier=self.supplier_a,
            unit_price=12.50, stock_quantity=3, reorder_level=5,
        )
        self.widget_b = Product.objects.create(
            sku='WD-1002', name='Widget B', supplier=self.supplier_b,
            unit_price=8.00, stock_quantity=40, reorder_level=10,
        )
        self.gizmo = Product.objects.create(
            sku='GZ-2001', name='Gizmo Pro', supplier=self.supplier_a,
            unit_price=25.00, stock_quantity=15, reorder_level=5,
        )

    def test_search_by_name(self):
        response = self.client.get(reverse('product_index'), {'q': 'widget'})
        products = list(response.context['products'])
        self.assertIn(self.widget_a, products)
        self.assertIn(self.widget_b, products)
        self.assertNotIn(self.gizmo, products)

    def test_search_by_sku(self):
        response = self.client.get(reverse('product_index'), {'q': 'GZ-2001'})
        products = list(response.context['products'])
        self.assertEqual(products, [self.gizmo])

    def test_supplier_filter(self):
        response = self.client.get(reverse('product_index'), {'supplier': self.supplier_a.id})
        products = list(response.context['products'])
        self.assertIn(self.widget_a, products)
        self.assertIn(self.gizmo, products)
        self.assertNotIn(self.widget_b, products)

    def test_price_range_filter(self):
        response = self.client.get(reverse('product_index'), {'min_price': '10', 'max_price': '20'})
        products = list(response.context['products'])
        self.assertEqual(products, [self.widget_a])

    def test_price_range_invalid_min(self):
        response = self.client.get(reverse('product_index'), {'min_price': 'abc'})
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('Min price must be a number' in str(m) for m in messages))

    def test_price_range_invalid_max(self):
        response = self.client.get(reverse('product_index'), {'max_price': 'xyz'})
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('Max price must be a number' in str(m) for m in messages))

    def test_pagination_first_page(self):
        for i in range(4, 25):
            Product.objects.create(
                sku=f'TST-{1000+i}', name=f'Test Product {i}',
                supplier=self.supplier_a, unit_price=10.00,
                stock_quantity=10, reorder_level=2,
            )
        response = self.client.get(reverse('product_index'))
        page_obj = response.context['page_obj']
        self.assertEqual(len(page_obj), 20)
        self.assertTrue(page_obj.has_next())
        self.assertFalse(page_obj.has_previous())

    def test_pagination_second_page(self):
        for i in range(4, 25):
            Product.objects.create(
                sku=f'TST-{1000+i}', name=f'Test Product {i}',
                supplier=self.supplier_a, unit_price=10.00,
                stock_quantity=10, reorder_level=2,
            )
        response = self.client.get(reverse('product_index'), {'page': 2})
        page_obj = response.context['page_obj']
        self.assertEqual(len(page_obj), 4)
        self.assertFalse(page_obj.has_next())
        self.assertTrue(page_obj.has_previous())
