from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Product, Supplier

User = get_user_model()


class SupplierFormTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.inventory_manager = User.objects.create_user(
            username='inventory_mgr',
            password='password123',
            role=User.ROLE_INVENTORY_MANAGER,
        )
        self.existing = Supplier.objects.create(
            name='Acme Corp',
            email='acme@example.com',
            phone='555-0100',
            address='123 Main St',
        )
        self.client = Client()

    def _valid_data(self, **overrides):
        data = {
            'name': 'New Supplier',
            'email': 'new@example.com',
            'phone': '555-0200',
            'address': '456 Oak Ave',
        }
        data.update(overrides)
        return data

    def test_create_form_displays_all_fields(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('supplier_create'))
        self.assertEqual(response.status_code, 200)
        for field in ('name', 'email', 'phone', 'address'):
            self.assertContains(response, f'name="{field}"')

    def test_create_valid_supplier(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(),
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.assertTrue(Supplier.objects.filter(email='new@example.com').exists())

    def test_create_rejects_empty_name(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(name=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Supplier.objects.filter(email='new@example.com').exists())
        self.assertFormError(response.context['form'], 'name', 'This field is required.')

    def test_create_rejects_invalid_email(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(email='not-an-email'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Supplier.objects.filter(name='New Supplier').exists())

    def test_create_rejects_duplicate_email(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(email='acme@example.com'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Supplier.objects.filter(email='acme@example.com').count(), 1)

    def test_edit_loads_existing_data(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('supplier_edit', args=[self.existing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Acme Corp')
        self.assertContains(response, 'acme@example.com')

    def test_edit_valid_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(
                name='Acme Updated',
                email='acme@example.com',
                phone='555-9999',
            ),
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, 'Acme Updated')
        self.assertEqual(self.existing.phone, '555-9999')

    def test_edit_allows_unchanged_email(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(
                name='Acme Renamed',
                email='acme@example.com',
            ),
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, 'Acme Renamed')

    def test_edit_rejects_other_suppliers_email(self):
        other = Supplier.objects.create(
            name='Other Co',
            email='other@example.com',
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(email=other.email),
        )
        self.assertEqual(response.status_code, 200)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.email, 'acme@example.com')

    def test_admin_can_create_and_edit(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('supplier_create')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('supplier_edit', args=[self.existing.pk])).status_code,
            200,
        )

    def test_sales_rep_can_view_suppliers(self):
        self.client.force_login(self.sales_rep)
        self.assertEqual(self.client.get(reverse('supplier_index')).status_code, 200)

    def test_sales_rep_cannot_create(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('supplier_create'))
        self.assertEqual(response.status_code, 403)

    def test_sales_rep_cannot_edit(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('supplier_edit', args=[self.existing.pk]))
        self.assertEqual(response.status_code, 403)

    def test_inventory_manager_can_view_suppliers(self):
        self.client.force_login(self.inventory_manager)
        self.assertEqual(self.client.get(reverse('supplier_index')).status_code, 200)

    def test_inventory_manager_can_create(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(email='inv-mgr@example.com'),
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.assertTrue(Supplier.objects.filter(email='inv-mgr@example.com').exists())

    def test_inventory_manager_can_edit(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(
                name='Updated by Inv Mgr',
                email='acme@example.com',
            ),
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, 'Updated by Inv Mgr')

    def test_inventory_manager_cannot_delete(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(
            reverse('supplier_delete', args=[self.existing.pk]),
        )
        self.assertEqual(response.status_code, 403)

    def test_supplier_index_shows_create_for_inventory_manager(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('supplier_index'))
        self.assertContains(response, reverse('supplier_create'))

    def test_supplier_index_hides_create_for_sales_rep(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('supplier_index'))
        self.assertNotContains(response, reverse('supplier_create'))

    def test_anonymous_cannot_create(self):
        response = self.client.get(reverse('supplier_create'))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('supplier_create')}",
        )

    def test_anonymous_cannot_edit(self):
        response = self.client.get(reverse('supplier_edit', args=[self.existing.pk]))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('supplier_edit', args=[self.existing.pk])}",
        )
    
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


class ProductEditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='product_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )

        self.sales_rep = User.objects.create_user(
            username='product_sales',
            password='password123',
            role=User.ROLE_SALES_REP,
        )

        self.supplier = Supplier.objects.create(
            name='Test Supplier',
            email='product-supplier@example.com',
        )

        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Test Product',
            unit_price=100.00,
            stock_quantity=20,
            reorder_level=5,
        )

        self.client = Client()

    def test_admin_can_open_product_edit(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('product_update', args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 200)
        class ProductEditTests(TestCase):
        self.assertContains(response, 'Test Product')

    def test_admin_can_update_product_stock_price_and_reorder_level(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('product_update', args=[self.product.pk]),
            {
                'supplier': self.supplier.pk,
                'name': 'Updated Product',
                'unit_price': '150.00',
                'stock_quantity': '10',
                'reorder_level': '3',
            },
        )

        self.assertRedirects(response, reverse('product_list'))

        self.product.refresh_from_db()

        self.assertEqual(self.product.name, 'Updated Product')
        self.assertEqual(float(self.product.unit_price), 150.00)
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertEqual(self.product.reorder_level, 3)

    def test_sales_rep_cannot_edit_product(self):
        self.client.force_login(self.sales_rep)

        response = self.client.get(
            reverse('product_update', args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 403)
