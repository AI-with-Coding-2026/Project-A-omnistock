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

    # ============================================================
    # TEST 1
    # Successful stock deduction
    # ============================================================

    def test_successful_stock_deduction(self):
        response = self.create_order(
            [self.product_a],
            [10],
        )

        self.assertRedirects(
            response,
            reverse('order_list'),
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            40,
        )

        self.assertEqual(
            Order.objects.count(),
            1,
        )

        self.assertEqual(
            OrderItem.objects.count(),
            1,
        )

        item = OrderItem.objects.get()

        self.assertEqual(
            item.product,
            self.product_a,
        )

        self.assertEqual(
            item.quantity,
            10,
        )

        self.assertEqual(
            item.unit_price,
            Decimal('100.00'),
        )

    # ============================================================
    # TEST 2
    # Insufficient stock
    # No order or stock changes
    # ============================================================

    def test_insufficient_stock_creates_no_order_or_stock_change(self):
        response = self.create_order(
            [self.product_a],
            [100],
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.assertEqual(
            OrderItem.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

    # ============================================================
    # TEST 3
    # Multiple products
    # ============================================================

    def test_multiple_products_deduct_stock_correctly(self):
        response = self.create_order(
            [self.product_a, self.product_b],
            [10, 5],
        )

        self.assertRedirects(
            response,
            reverse('order_list'),
        )

        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            40,
        )

        self.assertEqual(
            self.product_b.stock_quantity,
            25,
        )

        order = Order.objects.get()

        self.assertEqual(
            order.total_amount,
            Decimal('2252.50'),
        )

        self.assertEqual(
            OrderItem.objects.filter(order=order).count(),
            2,
        )

    # ============================================================
    # TEST 4
    # Duplicate product rows where combined quantity
    # EXCEEDS stock
    #
    # This is the bug Sir specifically identified.
    #
    # Stock = 50
    # Row 1 = 30
    # Row 2 = 30
    #
    # Individually:
    # 30 <= 50  -> passes
    # 30 <= 50  -> passes
    #
    # Combined:
    # 30 + 30 = 60
    # 60 > 50  -> MUST FAIL
    # ============================================================

    def test_duplicate_product_rows_combined_quantity_exceeds_stock(self):
        response = self.create_order(
            [
                self.product_a,
                self.product_a,
            ],
            [
                30,
                30,
            ],
            customer_name='Duplicate Overflow',
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.assertEqual(
            OrderItem.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

    # ============================================================
    # TEST 5
    # Duplicate product rows where combined quantity
    # IS WITHIN stock
    #
    # Stock = 50
    # Row 1 = 10
    # Row 2 = 15
    #
    # Combined = 25
    # 25 <= 50 -> MUST SUCCEED
    #
    # IMPORTANT:
    # Your current views.py intentionally creates TWO
    # OrderItems because it preserves the submitted line items.
    # Therefore this test checks two items, not one.
    # ============================================================

    def test_duplicate_product_rows_combined_quantity_within_stock_succeeds(self):
        response = self.create_order(
            [
                self.product_a,
                self.product_a,
            ],
            [
                10,
                15,
            ],
            customer_name='Duplicate Valid',
        )

        self.assertRedirects(
            response,
            reverse('order_list'),
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            25,
        )

        order = Order.objects.get(
            customer_name='Duplicate Valid',
        )

        self.assertEqual(
            order.total_amount,
            Decimal('2500.00'),
        )

        items = OrderItem.objects.filter(
            order=order,
            product=self.product_a,
        )

        # Current views.py preserves the two submitted rows.
        self.assertEqual(
            items.count(),
            2,
        )

        quantities = list(
            items.order_by('id').values_list(
                'quantity',
                flat=True,
            )
        )

        self.assertEqual(
            quantities,
            [10, 15],
        )

    # ============================================================
    # TEST 6
    # Duplicate product overflow + another valid product
    #
    # Product A:
    # 30 + 30 = 60 > 50
    #
    # Product B:
    # 5 <= 30
    #
    # Entire order MUST fail.
    # ============================================================

    def test_duplicate_product_overflow_rolls_back_entire_order(self):
        response = self.create_order(
            [
                self.product_a,
                self.product_a,
                self.product_b,
            ],
            [
                30,
                30,
                5,
            ],
            customer_name='Mixed Overflow',
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.assertEqual(
            OrderItem.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()
        self.product_b.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

        self.assertEqual(
            self.product_b.stock_quantity,
            30,
        )

    # ============================================================
    # TEST 7
    # Zero quantity rejected
    # ============================================================

    def test_zero_quantity_is_rejected(self):
        response = self.create_order(
            [self.product_a],
            [0],
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

    # ============================================================
    # TEST 8
    # Negative quantity rejected
    # ============================================================

    def test_negative_quantity_is_rejected(self):
        response = self.create_order(
            [self.product_a],
            [-5],
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

    # ============================================================
    # TEST 9
    # Invalid/non-numeric quantity rejected
    # ============================================================

    def test_non_numeric_quantity_is_rejected(self):
        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'Invalid Quantity',
                'items[][product]': [str(self.product_a.id)],
                'items[][quantity]': ['abc'],
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )

        self.product_a.refresh_from_db()

        self.assertEqual(
            self.product_a.stock_quantity,
            50,
        )

    # ============================================================
    # TEST 10
    # No line items rejected
    # ============================================================

    def test_no_line_items_are_rejected(self):
        response = self.client.post(
            reverse('order_create'),
            {
                'customer_name': 'No Items',
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Order.objects.count(),
            0,
        )