from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db.models import F
from django.template.loader import render_to_string
from django.test import RequestFactory, Client, TestCase
from django.urls import reverse, resolve

from inventory.models import Product, Supplier
from orders.models import Customer, InvalidOrderTransitionError, Invoice, Order, OrderItem
from orders.pdf import render_html_to_pdf


User = get_user_model()


class OrderCreateStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='SALES_REP',
        )
        self.customer = Customer.objects.create(
            name='Test Customer',
            email='customer@test.com',
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

    def create_order(self, products, quantities, customer=None):
        return self.client.post(
            reverse('order_create'),
            {
                'customer': (customer or self.customer).id,
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
        )

        self.assertRedirects(response, reverse('order_list'))

        self.product_a.refresh_from_db()

        self.assertEqual(self.product_a.stock_quantity, 25)

        order = Order.objects.get(customer=self.customer)

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
                'customer': self.customer.id,
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
                'customer': self.customer.id,
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
        self.customer = Customer.objects.create(
            name='Item Test Customer',
            email='itemtest@example.com',
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
                'customer': self.customer.id,
                'items[][product]': [
                    str(self.product_a.id),
                    str(self.product_b.id),
                ],
                'items[][quantity]': ['2', '3'],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('order_list'))

        order = Order.objects.get(customer=self.customer)

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
                'customer': self.customer.id,
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
                'customer': self.customer.id,
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['0'],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        response = self.client.post(
            reverse('order_create'),
            {
                'customer': self.customer.id,
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['-5'],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_rejects_order_with_no_items(self):
        self.login()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer': self.customer.id,
                'items[][product]': [''],
                'items[][quantity]': [''],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

        response = self.client.post(
            reverse('order_create'),
            {
                'customer': self.customer.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_product_id_no_partial_order(self):
        self.login()

        initial_order_count = Order.objects.count()
        initial_item_count = OrderItem.objects.count()

        response = self.client.post(
            reverse('order_create'),
            {
                'customer': self.customer.id,
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

    def test_pending_order_cancellation_restores_deducted_stock(self):
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
        Product.objects.filter(pk=self.product.pk).update(
            stock_quantity=F('stock_quantity') - 2,
        )
        self.product.refresh_from_db()

        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('order_cancel', args=[order.pk])
        )

        self.assertRedirects(response, reverse('order_list'))

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, 8)


class OrderStateMachineModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='model_tester',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.supplier = Supplier.objects.create(
            name='Model Supplier',
            email='model_supplier@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Model Product',
            unit_price=Decimal('20.00'),
            stock_quantity=10,
        )

    def create_order(self, status=Order.STATUS_PENDING):
        order = Order.objects.create(
            user=self.user,
            customer_name='Model Customer',
            status=status,
            total_amount=Decimal('40.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('20.00'),
        )
        Product.objects.filter(pk=self.product.pk).update(
            stock_quantity=F('stock_quantity') - 2,
        )
        self.product.refresh_from_db()
        return order

    def test_can_mark_completed(self):
        pending_order = self.create_order(status=Order.STATUS_PENDING)
        completed_order = self.create_order(status=Order.STATUS_COMPLETED)
        cancelled_order = self.create_order(status=Order.STATUS_CANCELLED)

        self.assertTrue(pending_order.can_mark_completed())
        self.assertFalse(completed_order.can_mark_completed())
        self.assertFalse(cancelled_order.can_mark_completed())

    def test_can_cancel(self):
        pending_order = self.create_order(status=Order.STATUS_PENDING)
        completed_order = self.create_order(status=Order.STATUS_COMPLETED)
        cancelled_order = self.create_order(status=Order.STATUS_CANCELLED)

        self.assertTrue(pending_order.can_cancel())
        self.assertTrue(completed_order.can_cancel())
        self.assertFalse(cancelled_order.can_cancel())

    def test_can_transition_to(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.assertTrue(order.can_transition_to(Order.STATUS_COMPLETED))
        self.assertTrue(order.can_transition_to(Order.STATUS_CANCELLED))
        self.assertFalse(order.can_transition_to(Order.STATUS_PENDING))

        order.status = Order.STATUS_COMPLETED
        self.assertTrue(order.can_transition_to(Order.STATUS_CANCELLED))
        self.assertFalse(order.can_transition_to(Order.STATUS_PENDING))
        self.assertFalse(order.can_transition_to(Order.STATUS_COMPLETED))

        order.status = Order.STATUS_CANCELLED
        self.assertFalse(order.can_transition_to(Order.STATUS_PENDING))
        self.assertFalse(order.can_transition_to(Order.STATUS_COMPLETED))
        self.assertFalse(order.can_transition_to(Order.STATUS_CANCELLED))

    def test_mark_completed_success(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        order.mark_completed()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_mark_completed_does_not_restore_or_deduct_stock(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        stock_before = Product.objects.get(pk=self.product.pk).stock_quantity

        order.mark_completed()
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(self.product.stock_quantity, stock_before)

    def test_mark_completed_raises_error_when_invalid(self):
        completed_order = self.create_order(status=Order.STATUS_COMPLETED)
        with self.assertRaises(InvalidOrderTransitionError):
            completed_order.mark_completed()

        cancelled_order = self.create_order(status=Order.STATUS_CANCELLED)
        with self.assertRaises(InvalidOrderTransitionError):
            cancelled_order.mark_completed()

    def test_cancel_from_completed_restores_stock(self):
        order = self.create_order(status=Order.STATUS_COMPLETED)
        initial_stock = self.product.stock_quantity
        order.cancel()
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, initial_stock + 2)

    def test_cancel_from_pending_restores_stock(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        initial_stock = self.product.stock_quantity
        order.cancel()
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, initial_stock + 2)

    def test_cancel_raises_error_on_cancelled_order(self):
        order = self.create_order(status=Order.STATUS_CANCELLED)
        with self.assertRaises(InvalidOrderTransitionError):
            order.cancel()

    def test_model_save_blocks_invalid_status_mutation(self):
        order = self.create_order(status=Order.STATUS_CANCELLED)
        order.status = Order.STATUS_PENDING
        with self.assertRaises(InvalidOrderTransitionError):
            order.save()

        completed_order = self.create_order(status=Order.STATUS_COMPLETED)
        completed_order.status = Order.STATUS_PENDING
        with self.assertRaises(InvalidOrderTransitionError):
            completed_order.save()

    def test_direct_save_completed_to_cancelled_restores_stock(self):
        """Any write path (e.g. Django admin) must restore stock, not just cancel()."""
        order = self.create_order(status=Order.STATUS_COMPLETED)
        initial_stock = Product.objects.get(pk=self.product.pk).stock_quantity

        order.status = Order.STATUS_CANCELLED
        order.save()

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, initial_stock + 2)

    def test_cancel_without_save_does_not_touch_stock(self):
        """Stock must never be restored unless the status change is persisted."""
        order = self.create_order(status=Order.STATUS_COMPLETED)
        initial_stock = Product.objects.get(pk=self.product.pk).stock_quantity

        order.cancel(save=False)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, initial_stock)
        self.assertEqual(
            Order.objects.get(pk=order.pk).status,
            Order.STATUS_COMPLETED,
        )

    def test_resaving_cancelled_order_does_not_restore_stock_again(self):
        """Stock restoration must be tied to the transition, not to every save."""
        order = self.create_order(status=Order.STATUS_COMPLETED)
        initial_stock = Product.objects.get(pk=self.product.pk).stock_quantity

        order.cancel()
        order.save()
        order.customer_name = 'Renamed Customer'
        order.save()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, initial_stock + 2)

    def test_cancelling_pending_order_restores_stock_via_save(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        initial_stock = Product.objects.get(pk=self.product.pk).stock_quantity

        order.status = Order.STATUS_CANCELLED
        order.save()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, initial_stock + 2)

    def test_full_clean_blocks_invalid_transition(self):
        """Admin/ModelForm validation path must reject terminal-state changes."""
        order = self.create_order(status=Order.STATUS_CANCELLED)
        order.status = Order.STATUS_PENDING

        with self.assertRaises(ValidationError):
            order.full_clean()


class OrderCompleteViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='complete_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='complete_sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.customer = User.objects.create_user(
            username='complete_customer',
            password='password123',
            role=User.ROLE_CUSTOMER,
            is_staff=False,
        )
        self.supplier = Supplier.objects.create(
            name='Complete Supplier',
            email='complete_supplier@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Complete Product',
            unit_price=Decimal('30.00'),
            stock_quantity=15,
        )

    def create_order(self, status=Order.STATUS_PENDING):
        order = Order.objects.create(
            user=self.admin,
            customer_name='Complete View Customer',
            status=status,
            total_amount=Decimal('60.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('30.00'),
        )
        return order

    def test_staff_can_mark_pending_order_completed(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.client.force_login(self.sales_rep)

        response = self.client.post(
            reverse('order_complete', args=[order.pk])
        )

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_admin_can_mark_pending_order_completed(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('order_complete', args=[order.pk])
        )

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_complete_does_not_modify_stock(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        Product.objects.filter(pk=self.product.pk).update(
            stock_quantity=F('stock_quantity') - 2,
        )
        self.product.refresh_from_db()
        stock_before_completion = self.product.stock_quantity

        self.client.force_login(self.sales_rep)
        response = self.client.post(
            reverse('order_complete', args=[order.pk])
        )

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertEqual(self.product.stock_quantity, stock_before_completion)

    def test_complete_view_blocks_already_completed_order(self):
        order = self.create_order(status=Order.STATUS_COMPLETED)
        self.client.force_login(self.sales_rep)

        with self.assertLogs('orders.views', level='WARNING') as cm:
            response = self.client.post(
                reverse('order_complete', args=[order.pk])
            )
            self.assertTrue(any('Invalid status transition attempted' in msg for msg in cm.output))

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_complete_view_blocks_cancelled_order(self):
        order = self.create_order(status=Order.STATUS_CANCELLED)
        self.client.force_login(self.sales_rep)

        with self.assertLogs('orders.views', level='WARNING') as cm:
            response = self.client.post(
                reverse('order_complete', args=[order.pk])
            )
            self.assertTrue(any('Invalid status transition attempted' in msg for msg in cm.output))

        self.assertRedirects(response, reverse('order_list'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)

    def test_unauthorized_user_cannot_complete_order(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse('order_complete', args=[order.pk])
        )

        self.assertIn(response.status_code, [302, 403])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)


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

    def test_cancelled_order_displays_red_status_badge(self):
        self.order.status = Order.STATUS_CANCELLED
        self.order.save()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancelled')
        self.assertContains(response, 'bg-red-100')

    def test_completed_order_displays_green_status_badge(self):
        self.order.status = Order.STATUS_COMPLETED
        self.order.save()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Completed')
        self.assertContains(response, 'bg-green-100')

    def test_order_detail_displays_multiple_line_items(self):
        second_product = Product.objects.create(
            supplier=self.supplier,
            name='Second Detail Product',
            unit_price=Decimal('15.00'),
            stock_quantity=20,
        )
        OrderItem.objects.create(
            order=self.order,
            product=second_product,
            quantity=3,
            unit_price=Decimal('15.00'),
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, second_product.name)
        self.assertContains(response, '2')
        self.assertContains(response, '3')

    def test_order_detail_shows_empty_state_when_no_items_exist(self):
        empty_order = Order.objects.create(
            user=self.user,
            customer_name='No Items Customer',
            total_amount=Decimal('0.00'),
            status=Order.STATUS_PENDING,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[empty_order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'No line items found for this order.',
        )

    def test_order_detail_returns_404_for_missing_order(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('order_detail', args=[99999])
        )

        self.assertEqual(response.status_code, 404)

    def test_user_without_an_allowed_role_is_redirected(self):
        unauthorized_user = User.objects.create_user(
            username='unauthorized_user',
            password='testpass123',
            role=User.ROLE_CUSTOMER,
        )
        self.client.force_login(unauthorized_user)

        detail_url = reverse('order_detail', args=[self.order.pk])
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f'{reverse("login")}?next={detail_url}',
        )


class OrderIndexTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='index_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='index_sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.customer = User.objects.create_user(
            username='index_customer',
            password='password123',
            role=User.ROLE_CUSTOMER,
        )
        self.order = Order.objects.create(
            user=self.admin,
            customer_name='Index Customer',
            total_amount=Decimal('99.99'),
            status=Order.STATUS_PENDING,
        )

    def test_staff_can_view_order_index_with_order_details(self):
        self.client.force_login(self.sales_rep)

        response = self.client.get(reverse('order_index'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/order_index.html')
        self.assertContains(response, self.order.order_number)
        self.assertContains(response, self.order.customer_name)
        self.assertContains(response, self.order.user.username)
        self.assertContains(response, str(self.order.total_amount))
        self.assertContains(response, self.order.created_at.strftime('%Y-%m-%d'))
        self.assertContains(response, self.order.get_status_display())
        self.assertContains(response, f'badge badge-{self.order.status}')

    def test_admin_can_view_order_index(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('order_index'))

        self.assertEqual(response.status_code, 200)

    def test_customer_is_redirected_to_login(self):
        self.client.force_login(self.customer)

        order_index_url = reverse('order_index')
        response = self.client.get(order_index_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f'{reverse("login")}?next={order_index_url}',
        )

    def test_filter_by_status(self):
        completed = Order.objects.create(
            user=self.admin,
            customer_name='Completed Customer',
            total_amount=Decimal('50.00'),
            status=Order.STATUS_COMPLETED,
        )

        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('order_index'), {'status': Order.STATUS_PENDING})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertNotContains(response, completed.order_number)

    def test_filter_by_customer_name(self):
        other = Order.objects.create(
            user=self.admin,
            customer_name='Other Customer',
            total_amount=Decimal('50.00'),
            status=Order.STATUS_PENDING,
        )

        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('order_index'), {'customer': 'Index'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertNotContains(response, other.order_number)


class InvoicePdfTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='pdf_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.supplier = Supplier.objects.create(
            name='PDF Supplier',
            email='pdf@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='PDF Product',
            unit_price=Decimal('12.50'),
            stock_quantity=40,
        )
        self.order = Order.objects.create(
            user=self.admin,
            customer_name='PDF Customer',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('25.00'),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('12.50'),
        )

    def test_invoice_pdf_downloads_as_pdf(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('invoice_pdf', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(
            response['Content-Disposition'].startswith('attachment;')
        )
        self.assertIn(
            f'invoice_{self.order.order_number}.pdf',
            response['Content-Disposition'],
        )
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_invoice_pdf_requires_allowed_role(self):
        unauthorized_user = User.objects.create_user(
            username='pdf_unauthorized',
            password='password123',
            role='CUSTOMER',
        )
        self.client.force_login(unauthorized_user)

        response = self.client.get(
            reverse('invoice_pdf', args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 302)

    def test_invoice_pdf_template_renders_order_data(self):
        self.product.sku = 'PDF-SKU-001'
        self.product.save()

        request = RequestFactory().get('/')
        request.resolver_match = resolve(reverse('order_list'))
        request.user = self.admin
        html = render_to_string(
            'orders/invoice.html',
            {'order': self.order},
            request=request,
        )

        self.assertIn('OmniStock', html)
        self.assertIn(self.order.customer_name, html)
        self.assertIn(self.order.order_number, html)
        self.assertIn('PDF Product', html)
        self.assertIn('PDF-SKU-001', html)
        self.assertIn('PDF Supplier', html)
        self.assertIn('status-completed', html)
        self.assertIn('$25.00', html)

    def test_invoice_pdf_template_converts_to_valid_pdf(self):
        request = RequestFactory().get('/')
        request.resolver_match = resolve(reverse('order_list'))
        request.user = self.admin
        html = render_to_string(
            'orders/invoice_pdf.html',
            {'order': self.order},
            request=request,
        )
        pdf_bytes = render_html_to_pdf(html)

        self.assertTrue(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_invoice_pdf_template_uses_invoice_number_when_present(self):
        invoice = Invoice.objects.create(order=self.order)

        request = RequestFactory().get('/')
        request.resolver_match = resolve(reverse('order_list'))
        request.user = self.admin
        html = render_to_string(
            'orders/invoice_pdf.html',
            {'order': self.order},
            request=request,
        )

        self.assertIn(invoice.invoice_number, html)
        self.assertNotIn(f'Invoice #:</strong> {self.order.pk}', html)

    def test_invoice_pdf_handles_generation_failure(self):
        self.client.force_login(self.admin)

        with patch('orders.views.render_html_to_pdf', return_value=b""):
            response = self.client.get(
                reverse('invoice_pdf', args=[self.order.pk])
            )

        self.assertRedirects(response, reverse('invoice_view', args=[self.order.pk]))
        follow_up = self.client.get(reverse('invoice_view', args=[self.order.pk]))
        self.assertEqual(follow_up.status_code, 200)


class OrderTransitionEndpointSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='security_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='security_sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.supplier = Supplier.objects.create(
            name='Security Supplier',
            email='security@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Security Product',
            unit_price=Decimal('30.00'),
            stock_quantity=15,
        )

    def create_order(self, status=Order.STATUS_PENDING):
        order = Order.objects.create(
            user=self.admin,
            customer_name='Security Customer',
            status=status,
            total_amount=Decimal('60.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('30.00'),
        )
        return order

    def test_complete_endpoint_rejects_get_requests(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.client.force_login(self.sales_rep)

        response = self.client.get(
            reverse('order_complete', args=[order.pk])
        )

        self.assertEqual(response.status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_cancel_endpoint_rejects_get_requests(self):
        order = self.create_order(status=Order.STATUS_PENDING)
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('order_cancel', args=[order.pk])
        )

        self.assertEqual(response.status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)


class OrderCancellationIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='idempotency_user',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.supplier = Supplier.objects.create(
            name='Idempotency Supplier',
            email='idempotency@example.com',
        )
        self.product_a = Product.objects.create(
            supplier=self.supplier,
            name='Idempotency Product A',
            unit_price=Decimal('10.00'),
            stock_quantity=50,
        )
        self.product_b = Product.objects.create(
            supplier=self.supplier,
            name='Idempotency Product B',
            unit_price=Decimal('20.00'),
            stock_quantity=30,
        )

    def test_cancel_restores_stock_exactly_once_per_item(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Multi Item Customer',
            status=Order.STATUS_PENDING,
            total_amount=Decimal('100.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_a,
            quantity=3,
            unit_price=Decimal('10.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_b,
            quantity=2,
            unit_price=Decimal('20.00'),
        )

        Product.objects.filter(pk=self.product_a.pk).update(
            stock_quantity=F('stock_quantity') - 3
        )
        Product.objects.filter(pk=self.product_b.pk).update(
            stock_quantity=F('stock_quantity') - 2
        )
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        initial_stock_a = self.product_a.stock_quantity
        initial_stock_b = self.product_b.stock_quantity

        order.cancel()
        order.refresh_from_db()
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product_a.stock_quantity, initial_stock_a + 3)
        self.assertEqual(self.product_b.stock_quantity, initial_stock_b + 2)

    def test_second_cancellation_via_view_does_not_restore_stock_again(self):
        order = Order.objects.create(
            user=self.user,
            customer_name='Double Cancel Customer',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('100.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_a,
            quantity=4,
            unit_price=Decimal('10.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_b,
            quantity=1,
            unit_price=Decimal('20.00'),
        )

        Product.objects.filter(pk=self.product_a.pk).update(
            stock_quantity=F('stock_quantity') - 4
        )
        Product.objects.filter(pk=self.product_b.pk).update(
            stock_quantity=F('stock_quantity') - 1
        )
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        initial_stock_a = self.product_a.stock_quantity
        initial_stock_b = self.product_b.stock_quantity

        self.client.force_login(self.user)
        self.client.post(reverse('order_cancel', args=[order.pk]))
        self.client.post(reverse('order_cancel', args=[order.pk]))

        order.refresh_from_db()
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product_a.stock_quantity, initial_stock_a + 4)
        self.assertEqual(self.product_b.stock_quantity, initial_stock_b + 1)

class CustomerCRUDTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='cust_admin',
            password='password123',
            role='ADMIN',
        )
        self.sales_rep = User.objects.create_user(
            username='cust_sales_rep',
            password='password123',
            role='SALES_REP',
        )
        self.inventory_manager = User.objects.create_user(
            username='cust_inv_mgr',
            password='password123',
            role='INVENTORY_MANAGER',
        )
        self.existing = Customer.objects.create(
            name='Existing Customer',
            email='existing@example.com',
            phone='555-0100',
        )

    def test_admin_can_list_customers(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Existing Customer')

    def test_sales_rep_can_list_customers(self):
        self.client.force_login(self.sales_rep)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 200)

    def test_inventory_manager_cannot_list_customers(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('customer_list'))
        self.assertEqual(response.status_code, 403)

    def test_sales_rep_can_create_customer(self):
        self.client.force_login(self.sales_rep)
        response = self.client.post(reverse('customer_create'), {
            'name': 'New Customer',
            'email': 'new@example.com',
            'phone': '555-0200',
            'address': '123 Main St',
        })
        self.assertRedirects(response, reverse('customer_list'))
        self.assertTrue(Customer.objects.filter(email='new@example.com').exists())

    def test_inventory_manager_cannot_create_customer(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('customer_create'))
        self.assertEqual(response.status_code, 403)

    def test_sales_rep_can_edit_customer(self):
        self.client.force_login(self.sales_rep)
        response = self.client.post(
            reverse('customer_update', args=[self.existing.pk]),
            {
                'name': 'Updated Name',
                'email': 'existing@example.com',
                'phone': '555-9999',
                'address': '',
            },
        )
        self.assertRedirects(response, reverse('customer_list'))
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, 'Updated Name')

    def test_inventory_manager_cannot_edit_customer(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('customer_update', args=[self.existing.pk]))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_customer_detail(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('customer_detail', args=[self.existing.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Existing Customer')

    def test_inventory_manager_cannot_view_customer_detail(self):
        self.client.force_login(self.inventory_manager)
        response = self.client.get(reverse('customer_detail', args=[self.existing.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('customer_list'))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('customer_list')}",
        )


class OrderCustomerIntegrationTests(TestCase):
    def setUp(self):
        self.sales_rep = User.objects.create_user(
            username='order_cust_rep',
            password='password123',
            role='SALES_REP',
        )
        self.supplier = Supplier.objects.create(
            name='Order Cust Supplier',
            email='ordercustsupplier@example.com',
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            name='Order Cust Product',
            unit_price=Decimal('20.00'),
            stock_quantity=50,
        )
        self.existing_customer = Customer.objects.create(
            name='Picked Customer',
            email='picked@example.com',
        )
        self.client.force_login(self.sales_rep)

    def test_order_created_with_existing_customer_sets_fk_and_snapshot(self):
        response = self.client.post(reverse('order_create'), {
            'customer': self.existing_customer.id,
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['2'],
        })

        self.assertRedirects(response, reverse('order_list'))

        order = Order.objects.latest('id')
        self.assertEqual(order.customer, self.existing_customer)
        self.assertEqual(order.customer_name, 'Picked Customer')

    def test_order_created_with_inline_new_customer_creates_customer_and_order(self):
        response = self.client.post(reverse('order_create'), {
            'new_customer_name': 'Inline Customer',
            'new_customer_email': 'inline@example.com',
            'new_customer_phone': '555-1234',
            'new_customer_address': '456 Oak Ave',
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['1'],
        })

        self.assertRedirects(response, reverse('order_list'))

        new_customer = Customer.objects.get(email='inline@example.com')
        self.assertEqual(new_customer.name, 'Inline Customer')
        self.assertEqual(new_customer.phone, '555-1234')

        order = Order.objects.latest('id')
        self.assertEqual(order.customer, new_customer)
        self.assertEqual(order.customer_name, 'Inline Customer')

    def test_order_without_customer_selection_or_inline_data_is_rejected(self):
        initial_count = Order.objects.count()
        response = self.client.post(reverse('order_create'), {
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['1'],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), initial_count)

    def test_inline_customer_not_created_if_order_validation_fails(self):
        """
        Per mentor's instruction: inline Customer creation and Order creation
        must be atomic. If line-item validation fails, no orphaned Customer
        should be created.
        """
        initial_customer_count = Customer.objects.count()

        response = self.client.post(reverse('order_create'), {
            'new_customer_name': 'Orphan Test',
            'new_customer_email': 'orphan@example.com',
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['9999'],  # exceeds stock
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.count(), initial_customer_count)
        self.assertFalse(Customer.objects.filter(email='orphan@example.com').exists())

    def test_customer_name_snapshot_does_not_change_when_customer_renamed_later(self):
        """
        Per mentor's instruction: customer_name is a point-in-time snapshot,
        not a live mirror of Customer.name.
        """
        response = self.client.post(reverse('order_create'), {
            'customer': self.existing_customer.id,
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['1'],
        })
        self.assertRedirects(response, reverse('order_list'))

        order = Order.objects.latest('id')
        self.assertEqual(order.customer_name, 'Picked Customer')

        # Rename the customer after the order was placed
        self.existing_customer.name = 'Renamed Later'
        self.existing_customer.save()

        order.refresh_from_db()
        self.assertEqual(order.customer_name, 'Picked Customer')  # unchanged
        self.assertEqual(order.customer.name, 'Renamed Later')  # FK reflects live data
    
    def test_inline_customer_duplicate_email_shows_friendly_error(self):
        response = self.client.post(reverse('order_create'), {
            'new_customer_name': 'Duplicate Attempt',
            'new_customer_email': self.existing_customer.email,  # already exists
            'items[][product]': [str(self.product.id)],
            'items[][quantity]': ['1'],
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
        self.assertEqual(
            Customer.objects.filter(email=self.existing_customer.email).count(),
            1,
        )