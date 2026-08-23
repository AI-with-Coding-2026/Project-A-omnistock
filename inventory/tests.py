from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from orders.models import Order, OrderItem
from .models import Product, Supplier

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
        self.supplier_a = Supplier.objects.create(name="Alpha Logistics", email="alpha@test.com", phone="543214367")
        self.supplier_b = Supplier.objects.create(name="Beta Supplies", email="info@beta.com", phone="567890432")
        self.supplier_c = Supplier.objects.create(name="Gamma Global", email="support@gamma.com", phone="543216789")

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

        self.url = reverse('supplier_index')

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


class ProductIndexViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_test', password='TestPass123!'
        )
        self.staff_user.role = 'STAFF'
        self.staff_user.save()
        self.client.force_login(self.staff_user)

        self.supplier_a = Supplier.objects.create(name='Acme Supplies', email='acme@example.com', phone='566473829')
        self.supplier_b = Supplier.objects.create(name='Widget Co', email='widgetco@example.com', phone='543672189')

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


    def test_create_rejects_empty_phone(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(phone=''),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Supplier.objects.filter(email='new@example.com').exists()
        )
        self.assertFormError(
            response.context['form'],
            'phone',
            'Phone number is required.'
        )

    def test_edit_rejects_empty_phone(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(phone=''),
        )

        self.assertEqual(response.status_code, 200)

        self.existing.refresh_from_db()
        self.assertEqual(self.existing.phone, '555-0100')

        self.assertFormError(
            response.context['form'],
            'phone',
            'Phone number is required.'
        )

    def test_create_rejects_invalid_phone(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(phone='abc'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Supplier.objects.filter(email='new@example.com').exists()
        )
        self.assertFormError(
            response.context['form'],
            'phone',
            'Enter a valid phone number.'
        )

    def test_edit_rejects_invalid_phone(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('supplier_edit', args=[self.existing.pk]),
            self._valid_data(phone='abc'),
        )

        self.assertEqual(response.status_code, 200)

        self.existing.refresh_from_db()
        self.assertEqual(self.existing.phone, '555-0100')

        self.assertFormError(
            response.context['form'],
            'phone',
            'Enter a valid phone number.'
        )

    def test_create_rejects_phone_without_digits(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('supplier_create'),
            self._valid_data(phone='---'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Supplier.objects.filter(email='new@example.com').exists()
        )
        self.assertFormError(
            response.context['form'],
            'phone',
            'Enter a valid phone number.'
        )
        
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
            phone='543678975'
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
        self.supplier = Supplier.objects.create(name="Test Supplier", email="test@supp.com", phone="567897654")

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


class ProtectedDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='password123',
            role='ADMIN',
        )
        self.client.force_login(self.admin)

        self.supplier = Supplier.objects.create(
            name='Test Supplier',
            email='supplier@test.com',
            phone='543533576'
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Test Product',
            unit_price=Decimal('50.00'),
            stock_quantity=10,
        )
        self.order = Order.objects.create(
            user=self.admin,
            customer_name='Customer',
            total_amount=Decimal('100.00'),
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('50.00'),
        )

    def test_delete_protected_product_redirects_with_error(self):
        """Deleting a product referenced by an OrderItem should not crash (500)."""
        response = self.client.post(
            reverse('product_delete', args=[self.product.pk])
        )
        self.assertRedirects(response, reverse('product_list'))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_delete_protected_supplier_redirects_with_error(self):
        """Deleting a supplier whose products are referenced by OrderItems should not crash (500)."""
        response = self.client.post(
            reverse('supplier_delete', args=[self.supplier.pk])
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())