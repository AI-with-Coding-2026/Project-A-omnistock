import csv
import io
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db.models import F
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from inventory.models import Product, Supplier
from orders.models import InvalidOrderTransitionError, Invoice, Order, OrderItem
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
        # Simulate stock deduction from order_create path
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

        order.refresh_from_db()
        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product_a.stock_quantity, initial_stock_a + 4)
        self.assertEqual(self.product_b.stock_quantity, initial_stock_b + 1)

class ReportsAndExportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='reports_admin',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.sales_rep = User.objects.create_user(
            username='reports_sales_rep',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        
        from inventory.models import Supplier, Product
        supplier = Supplier.objects.create(name='Test Supplier', email='test@supplier.com')
        self.prod_a = Product.objects.create(supplier=supplier, name='Prod A', unit_price=Decimal('10.00'), stock_quantity=100)
        self.prod_b = Product.objects.create(supplier=supplier, name='Prod B', unit_price=Decimal('20.00'), stock_quantity=100)

        self.january_order = self.create_order(
            'January Customer', Decimal('125.50'), Order.STATUS_COMPLETED,
            datetime(2026, 1, 15, tzinfo=timezone.get_current_timezone()),
            [(self.prod_a, 5), (self.prod_b, 2)]
        )
        self.january_order_two = self.create_order(
            'Second January Customer', Decimal('74.50'), Order.STATUS_COMPLETED,
            datetime(2026, 1, 28, tzinfo=timezone.get_current_timezone()),
            [(self.prod_a, 3)]
        )
        self.february_order = self.create_order(
            'February Customer', Decimal('300.00'), Order.STATUS_COMPLETED,
            datetime(2026, 2, 10, tzinfo=timezone.get_current_timezone()),
            [(self.prod_b, 10)]
        )
        self.pending_order = self.create_order(
            'Pending Customer', Decimal('999.00'), Order.STATUS_PENDING,
            datetime(2026, 1, 20, tzinfo=timezone.get_current_timezone()),
            [(self.prod_a, 50)] # Should not appear in top_products
        )
        self.cancelled_order = self.create_order(
            'Cancelled Customer', Decimal('100.00'), Order.STATUS_CANCELLED,
            datetime(2026, 1, 21, tzinfo=timezone.get_current_timezone()),
            [(self.prod_b, 100)] # Should not appear in top_products
        )

    def create_order(self, customer, total, status, created_at, items=None):
        order = Order.objects.create(
            user=self.sales_rep,
            customer_name=customer,
            total_amount=total,
            status=status,
        )
        if items:
            for product, qty in items:
                OrderItem.objects.create(
                    order=order, product=product, quantity=qty, unit_price=product.unit_price
                )

        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
        return order

    def test_admin_sees_completed_revenue_grouped_by_month_and_top_products(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/reports.html')
        
        # Check Monthly Revenue
        revenue = list(response.context['monthly_revenue'])
        self.assertEqual(len(revenue), 2)
        self.assertEqual(revenue[0]['month'].month, 1)
        self.assertEqual(revenue[0]['total'], Decimal('200.00'))
        self.assertEqual(revenue[1]['month'].month, 2)
        self.assertEqual(revenue[1]['total'], Decimal('300.00'))
        
        # Check Top Products (should exclude pending and cancelled orders)
        # Prod B: 2 (completed Jan) + 10 (completed Feb) = 12
        # Prod A: 5 (completed Jan) + 3 (completed Jan) = 8
        top_products = list(response.context['top_products'])
        self.assertEqual(len(top_products), 2)
        self.assertEqual(top_products[0]['product__name'], 'Prod B')
        self.assertEqual(top_products[0]['total_qty'], 12)
        self.assertEqual(top_products[1]['product__name'], 'Prod A')
        self.assertEqual(top_products[1]['total_qty'], 8)

        self.assertContains(response, 'Export Orders CSV')

    def test_reports_rejects_non_admin(self):
        self.client.force_login(self.sales_rep)

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 403)

    def test_export_contains_only_completed_orders(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('export_orders_csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="orders.csv"',
        )
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], [
            'Order #', 'Customer', 'Sales Rep', 'Total', 'Status', 'Created At',
        ])
        exported_numbers = {row[0] for row in rows[1:]}
        self.assertEqual(exported_numbers, {
            self.january_order.order_number,
            self.january_order_two.order_number,
            self.february_order.order_number,
        })
        self.assertNotIn(self.pending_order.order_number, exported_numbers)

    def test_export_rejects_non_admin(self):
        self.client.force_login(self.sales_rep)

        response = self.client.get(reverse('export_orders_csv'))

        self.assertEqual(response.status_code, 403)


class OrderStatusTransitionViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_t', password='pass123!', role='ADMIN')
        self.staff = User.objects.create_user(username='staff_t', password='pass123!', role='STAFF')
        self.sales_rep = User.objects.create_user(username='sales_t', password='pass123!', role='SALES_REP')

        from inventory.models import Product, Supplier
        supplier = Supplier.objects.create(name='Test Supplier', email='s@test.com', phone='111222333')
        self.product = Product.objects.create(
            sku='TST-1', name='Test Product', supplier=supplier,
            unit_price=10, stock_quantity=50, reorder_level=5,
        )

        self.pending_order = Order.objects.create(
            user=self.admin, customer_name='Pending Co', total_amount=100,
            status=Order.STATUS_PENDING,
        )
        OrderItem.objects.create(
            order=self.pending_order, product=self.product, quantity=5, unit_price=10,
        )

        self.completed_order = Order.objects.create(
            user=self.admin, customer_name='Completed Co', total_amount=100,
            status=Order.STATUS_COMPLETED,
        )
        OrderItem.objects.create(
            order=self.completed_order, product=self.product, quantity=5, unit_price=10,
        )

        self.cancelled_order = Order.objects.create(
            user=self.admin, customer_name='Cancelled Co', total_amount=100,
            status=Order.STATUS_CANCELLED,
        )

    # --- order_complete ---

    def test_staff_can_complete_pending_order(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('order_complete', args=[self.pending_order.pk]))
        self.pending_order.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pending_order.status, Order.STATUS_COMPLETED)

    def test_admin_can_complete_pending_order(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('order_complete', args=[self.pending_order.pk]))
        self.pending_order.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pending_order.status, Order.STATUS_COMPLETED)

    def test_complete_already_completed_order_shows_warning_no_crash(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('order_complete', args=[self.completed_order.pk]), follow=True)
        self.completed_order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.completed_order.status, Order.STATUS_COMPLETED)
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('cannot be marked as completed' in str(m) for m in messages))

    def test_complete_cancelled_order_blocked(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('order_complete', args=[self.cancelled_order.pk]), follow=True)
        self.cancelled_order.refresh_from_db()
        self.assertEqual(self.cancelled_order.status, Order.STATUS_CANCELLED)
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('cannot be marked as completed' in str(m) for m in messages))

    def test_unauthenticated_user_cannot_complete_order(self):
        response = self.client.post(reverse('order_complete', args=[self.pending_order.pk]))
        self.pending_order.refresh_from_db()
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(self.pending_order.status, Order.STATUS_PENDING)

    # --- order_cancel ---

    def test_admin_can_cancel_pending_order_and_stock_restored(self):
        self.product.stock_quantity = 45
        self.product.save()

        self.client.force_login(self.admin)
        response = self.client.post(reverse('order_cancel', args=[self.pending_order.pk]))
        self.pending_order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.pending_order.status, Order.STATUS_CANCELLED)
        self.assertEqual(self.product.stock_quantity, 50)

    def test_admin_can_cancel_completed_order(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('order_cancel', args=[self.completed_order.pk]))
        self.completed_order.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.completed_order.status, Order.STATUS_CANCELLED)

    def test_staff_cannot_cancel_order(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('order_cancel', args=[self.pending_order.pk]))
        self.pending_order.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.pending_order.status, Order.STATUS_PENDING)

    def test_sales_rep_cannot_cancel_order(self):
        self.client.force_login(self.sales_rep)
        response = self.client.post(reverse('order_cancel', args=[self.pending_order.pk]))
        self.assertEqual(response.status_code, 403)

    def test_cancel_already_cancelled_order_shows_warning(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('order_cancel', args=[self.cancelled_order.pk]), follow=True)
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('cannot be cancelled' in str(m) for m in messages))

class OrderListActionButtonsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_b', password='pass123!', role='ADMIN')
        self.staff = User.objects.create_user(username='staff_b', password='pass123!', role='STAFF')

        self.pending_order = Order.objects.create(
            user=self.admin, customer_name='Pending Co', total_amount=50,
            status=Order.STATUS_PENDING,
        )
        self.completed_order = Order.objects.create(
            user=self.admin, customer_name='Completed Co', total_amount=50,
            status=Order.STATUS_COMPLETED,
        )
        self.cancelled_order = Order.objects.create(
            user=self.admin, customer_name='Cancelled Co', total_amount=50,
            status=Order.STATUS_CANCELLED,
        )

    def test_staff_sees_complete_button_not_cancel_on_pending(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f"action=\"/orders/{self.pending_order.pk}/complete/\"", html)
        self.assertNotIn(f"action=\"/orders/{self.pending_order.pk}/cancel/\"", html)

    def test_admin_sees_both_buttons_on_pending(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f"action=\"/orders/{self.pending_order.pk}/complete/\"", html)
        self.assertIn(f"action=\"/orders/{self.pending_order.pk}/cancel/\"", html)

    def test_admin_sees_only_cancel_on_completed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(f"action=\"/orders/{self.completed_order.pk}/complete/\"", html)
        self.assertIn(f"action=\"/orders/{self.completed_order.pk}/cancel/\"", html)

    def test_no_action_buttons_on_cancelled(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(f"action=\"/orders/{self.cancelled_order.pk}/complete/\"", html)
        self.assertNotIn(f"action=\"/orders/{self.cancelled_order.pk}/cancel/\"", html)


class OrderAdvancedSearchAndFilterTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='filter_staff',
            password='password123',
            role=getattr(User, 'ROLE_STAFF', 'STAFF'),
        )
        self.client.force_login(self.staff_user)

        # إنشاء Supplier تجريبي للاختبار
        self.supplier = Supplier.objects.create(
            name='Test Supplier Tech',
            contact_email='supplier@test.com',
            phone_number='+1234567890',
        )

        self.product_laptop = Product.objects.create(
            name='Gaming Laptop',
            sku='LAP-001',
            unit_price=1200,
            stock_quantity=10,
            supplier=self.supplier,
        )
        self.product_mouse = Product.objects.create(
            name='Wireless Mouse',
            sku='MOU-002',
            unit_price=25,
            stock_quantity=50,
            supplier=self.supplier,
        )

        self.order1 = Order.objects.create(
            customer_name='Alice Smith',
            status='pending',
            user=self.staff_user,
        )
        OrderItem.objects.create(order=self.order1, product=self.product_laptop, quantity=1, unit_price=1200)

        self.order2 = Order.objects.create(
            customer_name='Bob Jones',
            status='completed',
            user=self.staff_user,
        )
        OrderItem.objects.create(order=self.order2, product=self.product_mouse, quantity=2, unit_price=25)

        self.order3 = Order.objects.create(
            customer_name='Charlie Brown',
            status='cancelled',
            user=self.staff_user,
        )
        OrderItem.objects.create(order=self.order3, product=self.product_mouse, quantity=1, unit_price=25)

        self.url = reverse('order_list')