

# Create your tests here.
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Product, Supplier
from orders.models import Order, OrderItem

User = get_user_model()


class OrderItemCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='SALES_REP',
        )

        self.supplier = Supplier.objects.create(
            name='Test Supplier',
            email='supplier@test.com',
        )

        self.product_a = Product.objects.create(
            supplier=self.supplier,
            name='Product A',
            unit_price=Decimal('100.00'),
            stock_quantity=50,
        )

        self.product_b = Product.objects.create(
            supplier=self.supplier,
            name='Product B',
            unit_price=Decimal('250.50'),
            stock_quantity=30,
        )

    def login(self):
        self.client.login(username='testuser', password='testpass123')

    # ── TEST 1: Multiple valid items + correct total_amount ──
    def test_create_order_with_multiple_items_calculates_total(self):
        self.login()

        response = self.client.post(reverse('order_create'), {
            'customer_name': 'John Doe',
            'items[][product]': [str(self.product_a.id), str(self.product_b.id)],
            'items[][quantity]': ['2', '3'],
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('order_list'))

        order = Order.objects.get(customer_name='John Doe')
        # 2 × 100.00 + 3 × 250.50 = 951.50
        self.assertEqual(order.total_amount, Decimal('951.50'))
        self.assertEqual(order.items.count(), 2)

        self.assertTrue(
            order.items.filter(
                product=self.product_a,
                quantity=2,
                unit_price=Decimal('100.00'),
            ).exists()
        )
        self.assertTrue(
            order.items.filter(
                product=self.product_b,
                quantity=3,
                unit_price=Decimal('250.50'),
            ).exists()
        )

    # ── TEST 2: Server uses DB price, ignores browser-provided value ──
    def test_uses_database_price_not_browser_value(self):
        self.login()

        response = self.client.post(reverse('order_create'), {
            'customer_name': 'Jane Doe',
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['1'],
            'items[][unit_price]': ['1.00'],  # Browser trying to manipulate
        })

        self.assertEqual(response.status_code, 302)

        item = OrderItem.objects.get(product=self.product_a)
        self.assertEqual(item.unit_price, Decimal('100.00'))

        self.assertFalse(
            OrderItem.objects.filter(
                product=self.product_a,
                unit_price=Decimal('1.00'),
            ).exists()
        )

    # ── TEST 3: Reject quantity 0 and negative quantities ──
    def test_rejects_zero_and_negative_quantity(self):
        self.login()

        # Zero quantity
        response = self.client.post(reverse('order_create'), {
            'customer_name': 'Test Zero',
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['0'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(customer_name='Test Zero').count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        # Negative quantity
        response = self.client.post(reverse('order_create'), {
            'customer_name': 'Test Negative',
            'items[][product]': [str(self.product_a.id)],
            'items[][quantity]': ['-5'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(customer_name='Test Negative').count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    # ── TEST 4: Reject order with no valid line items ──
    def test_rejects_order_with_no_items(self):
        self.login()

        # Empty strings
        response = self.client.post(reverse('order_create'), {
            'customer_name': 'No Items',
            'items[][product]': [''],
            'items[][quantity]': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(customer_name='No Items').count(), 0)

        # Missing item keys entirely
        response = self.client.post(reverse('order_create'), {
            'customer_name': 'Missing Items',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.filter(customer_name='Missing Items').count(), 0)

    # ── TEST 5: Invalid product ID without partial order in DB ──
    def test_invalid_product_id_no_partial_order(self):
        self.login()

        initial_order_count = Order.objects.count()
        initial_item_count = OrderItem.objects.count()
        invalid_id = 99999

        response = self.client.post(reverse('order_create'), {
            'customer_name': 'Invalid Product',
            'items[][product]': [str(self.product_a.id), str(invalid_id)],
            'items[][quantity]': ['2', '1'],
        })

        self.assertEqual(response.status_code, 404)

        # CRITICAL: No partial order or items left in DB
        self.assertEqual(Order.objects.count(), initial_order_count)
        self.assertEqual(OrderItem.objects.count(), initial_item_count)


class OrderCancellationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='cancel_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='cancel_sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.supplier = Supplier.objects.create(
            name='Cancellation Supplier',
            email='cancellation@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Cancellation Product',
            unit_price=Decimal('50.00'),
            stock_quantity=8,
        )

    def create_completed_order(self):
        order = Order.objects.create(
            user=self.admin,
            customer_name='Completed Customer',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('100.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('50.00'),
        )
        return order

    def test_admin_cancellation_restores_stock_and_updates_status(self):
        order = self.create_completed_order()
        self.client.force_login(self.admin)

        response = self.client.post(reverse('order_cancel', args=[order.pk]))

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, 10)

    def test_second_cancellation_does_not_restore_stock_twice(self):
        order = self.create_completed_order()
        self.client.force_login(self.admin)

        self.client.post(reverse('order_cancel', args=[order.pk]))
        self.client.post(reverse('order_cancel', args=[order.pk]))

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, 10)

    def test_non_admin_cannot_cancel_order(self):
        order = self.create_completed_order()
        self.client.force_login(self.sales_rep)

        response = self.client.post(reverse('order_cancel', args=[order.pk]))

        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(self.product.stock_quantity, 8)

    def test_pending_order_cannot_be_cancelled_or_restore_stock(self):
        order = Order.objects.create(
            user=self.admin,
            customer_name='Pending Customer',
            status=Order.STATUS_PENDING,
            total_amount=Decimal('100.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('50.00'),
        )
        self.client.force_login(self.admin)

        response = self.client.post(reverse('order_cancel', args=[order.pk]))

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(self.product.stock_quantity, 8)