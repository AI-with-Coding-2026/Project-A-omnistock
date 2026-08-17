from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Product, Supplier
from orders.models import Order, OrderItem


User = get_user_model()


class OrderCreateStockTests(TestCase):
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

        self.client.login(
            username='testuser',
            password='testpass123',
        )

    def create_order(self, products, quantities, customer_name='Test Customer'):
        return self.client.post(
            reverse('order_create'),
            {
                'customer_name': customer_name,
                'items[][product]': [str(product.id) for product in products],
                'items[][quantity]': [str(quantity) for quantity in quantities],
            },
        )
     

    def test_successful_stock_deduction(self):
        response = self.create_order([self.product_a], [10])

        self.assertRedirects(response, reverse('order_list'))

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 40)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

        item = OrderItem.objects.get()

        self.assertEqual(item.product, self.product_a)
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.unit_price, Decimal('100.00'))


    def test_insufficient_stock_creates_no_order_or_stock_change(self):
        response = self.create_order([self.product_a], [100])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)


    def test_multiple_products_deduct_stock_correctly(self):
        response = self.create_order(
            [self.product_a, self.product_b],
            [10, 5],
        )

        self.assertRedirects(response, reverse('order_list'))

        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 40)
        self.assertEqual(self.product_b.stock_quantity, 25)

        order = Order.objects.get()

        self.assertEqual(order.total_amount, Decimal('2252.50'))
        self.assertEqual(OrderItem.objects.filter(order=order).count(), 2)



    def test_duplicate_product_rows_combined_quantity_exceeds_stock(self):
        response = self.create_order(
            [self.product_a, self.product_a],
            [30, 30],
            customer_name='Duplicate Overflow',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)

  

    def test_duplicate_product_rows_combined_quantity_within_stock_succeeds(self):
        response = self.create_order(
            [self.product_a, self.product_a],
            [10, 15],
            customer_name='Duplicate Valid',
        )

        self.assertRedirects(response, reverse('order_list'))

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 25)

        order = Order.objects.get(customer_name='Duplicate Valid')

        self.assertEqual(order.total_amount, Decimal('2500.00'))

        items = OrderItem.objects.filter(
            order=order,
            product=self.product_a,
        )

        
        self.assertEqual(items.count(), 2)

        quantities = list(
            items.order_by('id').values_list(
                'quantity',
                flat=True,
            )
        )

        self.assertEqual(quantities, [10, 15])


    def test_duplicate_product_overflow_rolls_back_entire_order(self):
        response = self.create_order(
            [self.product_a, self.product_a, self.product_b],
            [30, 30, 5],
            customer_name='Mixed Overflow',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)
        self.assertEqual(self.product_b.stock_quantity, 30)



    def test_zero_quantity_is_rejected(self):
        response = self.create_order([self.product_a], [0])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)


    def test_negative_quantity_is_rejected(self):
        response = self.create_order([self.product_a], [-5])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)


    def test_non_numeric_quantity_is_rejected(self):
        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Invalid Quantity',
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['abc'],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 50)


    def test_no_line_items_are_rejected(self):
        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'No Items',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)


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
        self.client.login(
            username='testuser',
            password='testpass123',
        )

    def test_create_order_with_multiple_items_calculates_total(self):
        self.login()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'John Doe',
                'items[][product]': [
                    str(self.product_a.id),
                    str(self.product_b.id),
                ],
                'items[][quantity]': ['2', '3'],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('order_list'))

        order = Order.objects.get(customer_name='John Doe')

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

    def test_uses_database_price_not_browser_value(self):
        self.login()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Jane Doe',
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['1'],
                'items[][unit_price]': ['1.00'],
            },
        )

        self.assertEqual(response.status_code, 302)

        item = OrderItem.objects.get(product=self.product_a)

        self.assertEqual(item.unit_price, Decimal('100.00'))
        self.assertFalse(
            OrderItem.objects.filter(
                product=self.product_a,
                unit_price=Decimal('1.00'),
            ).exists()
        )

    def test_rejects_zero_and_negative_quantity(self):
        self.login()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Test Zero',
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['0'],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.filter(customer_name='Test Zero').count(),
            0,
        )
        self.assertEqual(OrderItem.objects.count(), 0)

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Test Negative',
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['-5'],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.filter(customer_name='Test Negative').count(),
            0,
        )
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_rejects_order_with_no_items(self):
        self.login()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'No Items',
                'items[][product]': [''],
                'items[][quantity]': [''],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.filter(customer_name='No Items').count(),
            0,
        )

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Missing Items',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.filter(customer_name='Missing Items').count(),
            0,
        )

    def test_invalid_product_id_no_partial_order(self):
        self.login()

        initial_order_count = Order.objects.count()
        initial_item_count = OrderItem.objects.count()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Invalid Product',
                'items[][product]': [
                    str(self.product_a.id),
                    '99999',
                ],
                'items[][quantity]': ['2', '1'],
            },
        )

        self.assertEqual(response.status_code, 404)
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

        response = self.client.post(
            reverse('order_cancel', args=[order.pk])
        )

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

        response = self.client.post(
            reverse('order_cancel', args=[order.pk])
        )

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

        response = self.client.post(
            reverse('order_cancel', args=[order.pk])
        )

        self.assertRedirects(response, reverse('order_list'))

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(self.product.stock_quantity, 8)

class OrderDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='detail_user',
            password='testpass123',
            role=User.ROLE_STAFF,
        )
        self.supplier = Supplier.objects.create(
            name='Detail Supplier',
            email='detail@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Detail Product',
            unit_price=Decimal('25.00'),
            stock_quantity=10,
        )
        self.order = Order.objects.create(
            user=self.user,
            customer_name='Detail Customer',
            total_amount=Decimal('50.00'),
            status=Order.STATUS_COMPLETED,
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('25.00'),
        )

    def test_staff_can_view_order_detail_with_line_items(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertContains(response, 'Detail Customer')
        self.assertContains(response, 'Detail Product')
        self.assertContains(response, '25.00')