from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from orders.models import Order, OrderItem
from .models import InvalidPurchaseOrderTransitionError, Product, PurchaseOrder, PurchaseOrderItem, Supplier

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

    def test_delete_protected_product_redirects_with_red_error_message(self):
        """Deleting a product referenced by an OrderItem should not crash (500)."""
        response = self.client.post(
            reverse('product_delete', args=[self.product.pk]),
            follow=True,
        )
        self.assertRedirects(response, reverse('product_list'))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].tags, 'error')
        self.assertIn(
            'This product cannot be deleted because it is referenced by existing order history.',
            str(messages[0]),
        )

        # Confirms the rendered banner uses the red error styling.
        self.assertContains(response, 'bg-red-50')
        self.assertContains(response, 'text-red-800')


    def test_delete_unreferenced_product_redirects_with_green_success_message(self):
        deletable_product = Product.objects.create(
            supplier=self.supplier,
            name='Deletable Product',
            unit_price=Decimal('25.00'),
            stock_quantity=5,
        )

        response = self.client.post(
            reverse('product_delete', args=[deletable_product.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('product_list'))
        self.assertFalse(Product.objects.filter(pk=deletable_product.pk).exists())

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].tags, 'success')
        self.assertIn('Product deleted.', str(messages[0]))

        # Confirms the rendered success banner remains green.
        self.assertContains(response, 'bg-green-50')
        self.assertContains(response, 'text-green-800')

    def test_delete_protected_supplier_redirects_with_error(self):
        """Deleting a supplier whose products are referenced by OrderItems should not crash (500)."""
        response = self.client.post(
            reverse('supplier_delete', args=[self.supplier.pk])
        )
        self.assertRedirects(response, reverse('supplier_index'))
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())


class PurchaseOrderModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='po_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.supplier = Supplier.objects.create(
            name='PO Supplier',
            email='po_supplier@test.com',
            phone='123456789',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='PO Product',
            unit_price=Decimal('50.00'),
            stock_quantity=10,
        )

    def test_po_str_includes_number_and_supplier(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
            status=PurchaseOrder.STATUS_PENDING,
        )
        self.assertIn(po.po_number, str(po))
        self.assertIn(self.supplier.name, str(po))

    def test_po_number_auto_generated(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        self.assertTrue(po.po_number.startswith('PO-'))
        self.assertEqual(po.status, PurchaseOrder.STATUS_PENDING)

    def test_line_total_property(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=self.product,
            quantity=3,
            unit_cost=Decimal('25.00'),
        )
        self.assertEqual(item.line_total(), Decimal('75.00'))

    def test_rejects_zero_quantity(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        item = PurchaseOrderItem(
            purchase_order=po,
            product=self.product,
            quantity=0,
            unit_cost=Decimal('10.00'),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_rejects_negative_quantity(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        item = PurchaseOrderItem(
            purchase_order=po,
            product=self.product,
            quantity=-1,
            unit_cost=Decimal('10.00'),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_rejects_negative_unit_cost(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        item = PurchaseOrderItem(
            purchase_order=po,
            product=self.product,
            quantity=1,
            unit_cost=Decimal('-1.00'),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_allows_zero_unit_cost(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        item = PurchaseOrderItem(
            purchase_order=po,
            product=self.product,
            quantity=1,
            unit_cost=Decimal('0.00'),
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.unit_cost, Decimal('0.00'))


class PurchaseOrderAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='po_access_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.inventory_manager = User.objects.create_user(
            username='po_access_inv_mgr',
            password='password123',
            role=User.ROLE_INVENTORY_MANAGER,
        )
        self.sales_rep = User.objects.create_user(
            username='po_access_sales',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.staff = User.objects.create_user(
            username='po_access_staff',
            password='password123',
            role=User.ROLE_STAFF,
        )
        self.customer = User.objects.create_user(
            username='po_access_customer',
            password='password123',
            role=User.ROLE_CUSTOMER,
        )
        self.supplier = Supplier.objects.create(
            name='Access Supplier',
            email='access_supplier@test.com',
            phone='123456789',
        )
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
        )
        self.client = Client()

    def test_admin_can_access_create(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_list(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_manager_can_access_create(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_manager_can_access_list(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)

    def test_sales_rep_cannot_access_create(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 403)

    def test_sales_rep_cannot_access_list(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_access_create(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_access_list(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_access_create(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_access_list(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login_for_create(self):
        response = self.client.get(reverse('purchase_order_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(reverse('login')), response.url)

    def test_anonymous_redirected_to_login_for_list(self):
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(reverse('login')), response.url)


class PurchaseOrderCreateFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='po_flow_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.inventory_manager = User.objects.create_user(
            username='po_flow_inv_mgr',
            password='password123',
            role=User.ROLE_INVENTORY_MANAGER,
        )
        self.supplier = Supplier.objects.create(
            name='Flow Supplier',
            email='flow_supplier@test.com',
            phone='123456789',
        )
        self.product_a = Product.objects.create(
            supplier=self.supplier,
            name='Product A',
            unit_price=Decimal('10.00'),
            stock_quantity=100,
        )
        self.product_b = Product.objects.create(
            supplier=self.supplier,
            name='Product B',
            unit_price=Decimal('20.00'),
            stock_quantity=100,
        )
        self.client = Client()

    def _post_po(self, user, data):
        self.client.force_login(user)
        return self.client.post(reverse('purchase_order_create'), data)

    def test_valid_post_creates_po_pending_with_created_by(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['5'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        po = PurchaseOrder.objects.first()
        self.assertEqual(po.status, PurchaseOrder.STATUS_PENDING)
        self.assertEqual(po.created_by, self.admin)
        self.assertEqual(po.supplier, self.supplier)
        self.assertEqual(po.items.count(), 1)
        item = po.items.first()
        self.assertEqual(item.product, self.product_a)
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.unit_cost, Decimal('10.00'))

    def test_multiple_line_items_all_saved(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id), str(self.product_b.id)],
            'items[][quantity]': ['2', '3'],
            'items[][unit_cost]': ['10.00', '20.00'],
            'items[][is_new]': ['', ''],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        po = PurchaseOrder.objects.first()
        self.assertEqual(po.items.count(), 2)
        items = list(po.items.all())
        self.assertEqual(items[0].product, self.product_a)
        self.assertEqual(items[0].quantity, 2)
        self.assertEqual(items[1].product, self.product_b)
        self.assertEqual(items[1].quantity, 3)

    def test_zero_items_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': [''],
            'items[][unit_cost]': [''],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_new_product_line_item_creates_product(self):
        initial_product_count = Product.objects.count()
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': ['', str(self.product_a.id)],
            'items[][quantity]': ['1', '2'],
            'items[][unit_cost]': ['15.00', '10.00'],
            'items[][is_new]': ['on', ''],
            'items[][new_product_name]': ['New Widget', ''],
            'items[][new_product_price]': ['15.00', ''],
            'items[][new_product_stock]': ['50', ''],
            'items[][new_product_reorder]': ['10', ''],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        self.assertEqual(Product.objects.count(), initial_product_count + 1)
        new_product = Product.objects.filter(name='New Widget').first()
        self.assertIsNotNone(new_product)
        self.assertEqual(new_product.supplier, self.supplier)
        self.assertTrue(new_product.sku.startswith('SUP-PROD-'))
        po = PurchaseOrder.objects.first()
        self.assertEqual(po.items.count(), 2)
        self.assertTrue(po.items.filter(product=new_product, quantity=1, unit_cost=Decimal('15.00')).exists())

    def test_no_stock_quantity_side_effects_on_creation(self):
        original_stock = self.product_a.stock_quantity
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['10'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock_quantity, original_stock)

    def test_inventory_manager_can_create_po(self):
        response = self._post_po(self.inventory_manager, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['3'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        po = PurchaseOrder.objects.first()
        self.assertEqual(po.created_by, self.inventory_manager)
        self.assertEqual(po.status, PurchaseOrder.STATUS_PENDING)

    def test_negative_quantity_post_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['-5'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_negative_unit_cost_post_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['5'],
            'items[][unit_cost]': ['-10.00'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_non_numeric_quantity_post_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['abc'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_invalid_second_item_rolls_back_new_product_creation(self):
        initial_product_count = Product.objects.count()
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': ['', str(self.product_a.id)],
            'items[][quantity]': ['1', '-5'],
            'items[][unit_cost]': ['15.00', '10.00'],
            'items[][is_new]': ['on', ''],
            'items[][new_product_name]': ['Rollback Widget', ''],
            'items[][new_product_price]': ['15.00', ''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertEqual(Product.objects.count(), initial_product_count)
        self.assertFalse(Product.objects.filter(name='Rollback Widget').exists())

    def test_nan_unit_cost_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['NaN'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_negative_new_product_stock_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['15.00'],
            'items[][is_new]': ['on'],
            'items[][new_product_name]': ['Negative Stock Widget'],
            'items[][new_product_price]': ['15.00'],
            'items[][new_product_stock]': ['-10'],
            'items[][new_product_reorder]': ['0'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertFalse(Product.objects.filter(name='Negative Stock Widget').exists())

    def test_negative_new_product_reorder_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['15.00'],
            'items[][is_new]': ['on'],
            'items[][new_product_name]': ['Negative Reorder Widget'],
            'items[][new_product_price]': ['15.00'],
            'items[][new_product_stock]': ['10'],
            'items[][new_product_reorder]': ['-5'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertFalse(Product.objects.filter(name='Negative Reorder Widget').exists())

    def test_non_existent_product_id_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': ['99999'],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['10.00'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_infinity_unit_cost_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['Infinity'],
            'items[][is_new]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_infinity_new_product_price_rejected(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['15.00'],
            'items[][is_new]': ['on'],
            'items[][new_product_name]': ['Infinity Price Widget'],
            'items[][new_product_price]': ['Infinity'],
            'items[][new_product_stock]': ['10'],
            'items[][new_product_reorder]': ['5'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertFalse(Product.objects.filter(name='Infinity Price Widget').exists())

    def test_new_product_name_too_long_rejected(self):
        long_name = 'X' * 300
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': ['1'],
            'items[][unit_cost]': ['15.00'],
            'items[][is_new]': ['on'],
            'items[][new_product_name]': [long_name],
            'items[][new_product_price]': ['15.00'],
            'items[][new_product_stock]': ['10'],
            'items[][new_product_reorder]': ['5'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PurchaseOrder.objects.count(), 0)
        self.assertFalse(Product.objects.filter(name=long_name).exists())

    def test_new_product_name_null_byte_is_stripped(self):
        response = self._post_po(self.admin, {
            'supplier': str(self.supplier.id),
            'items[][product]': [''],
            'items[][quantity]': ['2'],
            'items[][unit_cost]': ['15.00'],
            'items[][is_new]': ['on'],
            'items[][new_product_name]': ['Widget\x00X'],
            'items[][new_product_price]': ['15.00'],
            'items[][new_product_stock]': ['10'],
            'items[][new_product_reorder]': ['5'],
        })
        self.assertRedirects(response, reverse('purchase_order_list'))
        self.assertTrue(Product.objects.filter(name='WidgetX').exists())


class PurchaseOrderListViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='po_list_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.inventory_manager = User.objects.create_user(
            username='po_list_inv_mgr',
            password='password123',
            role=User.ROLE_INVENTORY_MANAGER,
        )
        self.sales_rep = User.objects.create_user(
            username='po_list_sales',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.supplier = Supplier.objects.create(
            name='List Supplier',
            email='list_supplier@test.com',
            phone='123456789',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='List Product',
            unit_price=Decimal('10.00'),
            stock_quantity=100,
        )
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.admin,
            status=PurchaseOrder.STATUS_PENDING,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=self.po,
            product=self.product,
            quantity=5,
            unit_cost=Decimal('10.00'),
        )
        self.client = Client()

    def test_new_po_shows_in_list(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.po.po_number)
        self.assertContains(response, self.supplier.name)
        self.assertContains(response, 'Pending')

    def test_shows_created_by_username(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin.username)

    def test_shows_created_at(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.po.created_at.strftime('%b %d, %Y'))

    def test_sales_rep_cannot_access_list(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 403)

    def test_inventory_manager_can_access_list(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)

class SupplierPortalPOResponseTests(TestCase):
    def setUp(self):
        self.supplier_a = Supplier.objects.create(
            name='Alpha Logistics', email='alpha@test.com', phone='543214367'
        )
        self.supplier_b = Supplier.objects.create(
            name='Beta Supplies', email='info@beta.com', phone='567890432'
        )

        self.supplier_a_user = User.objects.create_user(
            username='supplier_a_user', password='TestPass123!', role='SUPPLIER'
        )
        self.supplier_a.user = self.supplier_a_user
        self.supplier_a.save()

        self.supplier_b_user = User.objects.create_user(
            username='supplier_b_user', password='TestPass123!', role='SUPPLIER'
        )
        self.supplier_b.user = self.supplier_b_user
        self.supplier_b.save()

        self.unlinked_supplier_user = User.objects.create_user(
            username='unlinked_supplier_user', password='TestPass123!', role='SUPPLIER'
        )

        self.admin = User.objects.create_user(
            username='admin_user', password='TestPass123!', role='ADMIN'
        )
        self.inventory_manager = User.objects.create_user(
            username='inv_mgr_user', password='TestPass123!', role='INVENTORY_MANAGER'
        )

        self.product = Product.objects.create(
            sku='WD-1001', name='Widget A', supplier=self.supplier_a,
            unit_price=Decimal('10.00'), stock_quantity=50, reorder_level=5,
        )

        self.po_a = PurchaseOrder.objects.create(
            supplier=self.supplier_a, created_by=self.admin,
            status=PurchaseOrder.STATUS_PENDING,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=self.po_a, product=self.product,
            quantity=5, unit_cost=Decimal('10.00'),
        )

        self.po_b = PurchaseOrder.objects.create(
            supplier=self.supplier_b, created_by=self.admin,
            status=PurchaseOrder.STATUS_PENDING,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=self.po_b, product=self.product,
            quantity=3, unit_cost=Decimal('10.00'),
        )

    def test_linked_supplier_sees_only_own_pos(self):
        self.client.force_login(self.supplier_a_user)
        response = self.client.get(reverse('supplier_portal_po_list'))
        self.assertEqual(response.status_code, 200)
        purchase_orders = list(response.context['purchase_orders'])
        self.assertIn(self.po_a, purchase_orders)
        self.assertNotIn(self.po_b, purchase_orders)

    def test_supplier_cannot_accept_another_suppliers_po(self):
        self.client.force_login(self.supplier_a_user)
        response = self.client.post(
            reverse('supplier_portal_po_accept', args=[self.po_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.po_b.refresh_from_db()
        self.assertEqual(self.po_b.status, PurchaseOrder.STATUS_PENDING)

    def test_supplier_cannot_reject_another_suppliers_po(self):
        self.client.force_login(self.supplier_a_user)
        response = self.client.post(
            reverse('supplier_portal_po_reject', args=[self.po_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.po_b.refresh_from_db()
        self.assertEqual(self.po_b.status, PurchaseOrder.STATUS_PENDING)

    def test_supplier_can_accept_own_po(self):
        self.client.force_login(self.supplier_a_user)
        response = self.client.post(
            reverse('supplier_portal_po_accept', args=[self.po_a.pk])
        )
        self.assertRedirects(response, reverse('supplier_portal_po_list'))
        self.po_a.refresh_from_db()
        self.assertEqual(self.po_a.status, PurchaseOrder.STATUS_APPROVED)

    def test_supplier_can_reject_own_po(self):
        self.client.force_login(self.supplier_a_user)
        response = self.client.post(
            reverse('supplier_portal_po_reject', args=[self.po_a.pk])
        )
        self.assertRedirects(response, reverse('supplier_portal_po_list'))
        self.po_a.refresh_from_db()
        self.assertEqual(self.po_a.status, PurchaseOrder.STATUS_CANCELLED)

    def test_accept_only_available_while_pending(self):
        self.po_a.status = PurchaseOrder.STATUS_APPROVED
        self.po_a.save(update_fields=['status'])
        self.client.force_login(self.supplier_a_user)
        response = self.client.post(
            reverse('supplier_portal_po_accept', args=[self.po_a.pk])
        )
        self.assertRedirects(response, reverse('supplier_portal_po_list'))
        self.po_a.refresh_from_db()
        self.assertEqual(self.po_a.status, PurchaseOrder.STATUS_APPROVED)

    def test_unlinked_supplier_user_denied(self):
        self.client.force_login(self.unlinked_supplier_user)
        response = self.client.get(reverse('supplier_portal_po_list'))
        self.assertEqual(response.status_code, 403)

    def test_unlinked_supplier_cannot_accept(self):
        self.client.force_login(self.unlinked_supplier_user)
        response = self.client.post(
            reverse('supplier_portal_po_accept', args=[self.po_a.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_non_supplier_role_cannot_access_portal(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('supplier_portal_po_list'))
        self.assertEqual(response.status_code, 403)

    def test_admin_purchase_order_list_unaffected(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)
        purchase_orders = list(response.context['purchase_orders'])
        self.assertIn(self.po_a, purchase_orders)
        self.assertIn(self.po_b, purchase_orders)

    def test_inventory_manager_purchase_order_list_unaffected(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('purchase_order_list'))
        self.assertEqual(response.status_code, 200)
        purchase_orders = list(response.context['purchase_orders'])
        self.assertIn(self.po_a, purchase_orders)
        self.assertIn(self.po_b, purchase_orders)
