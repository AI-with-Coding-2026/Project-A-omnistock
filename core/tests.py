from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from orders.models import Order
from .models import User
from core.utils import (
    admin_required,
    admin_or_inventory_manager_required,
    staff_or_admin_required,
)


class LandingAndAuthRoutingTests(TestCase):
    """
    Covers PR #66 review requirements:
    root routing, dashboard redirect, and auth redirect behavior.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin_route_test",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )

    # 1. Anonymous GET / returns the landing page
    def test_anonymous_get_root_returns_landing_page(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/landing.html')

    # 2. Authenticated GET / has explicit intended behavior
    # (decided: redirect straight to dashboard)
    def test_authenticated_get_root_redirects_to_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('landing'))
        self.assertRedirects(response, reverse('dashboard'))

    # 3. Anonymous GET /dashboard/ redirects to login
    def test_anonymous_get_dashboard_redirects_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    # 4. Authenticated GET /dashboard/ renders the dashboard
    def test_authenticated_get_dashboard_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/dashboard.html')

    # 5. Successful login redirects to /dashboard/
    def test_successful_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin_route_test',
            'password': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('dashboard'))

    # 6. Logout has the intended redirect destination
    def test_logout_redirects_to_login(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        # 7. Existing Products, Suppliers, Purchase Orders, Orders, Reports
    # routes still resolve for an authorized (admin) user
    def test_existing_module_routes_still_resolve(self):
        self.client.force_login(self.admin)

        routes = [
            'product_list',
            'supplier_index',
            'purchase_order_list',
            'order_list',
            'reports',
        ]

        for name in routes:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    # 8. Role-specific sidebar visibility/access remains correct
    def test_sidebar_links_visible_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Purchase Orders')
        self.assertContains(response, 'Reports')
        self.assertNotContains(response, 'Products (View)')

    def test_sidebar_links_hidden_for_sales_rep(self):
        sales_rep = User.objects.create_user(
            username="sales_route_test",
            password="StrongPass123!",
            role=User.ROLE_SALES_REP,
        )
        self.client.force_login(sales_rep)
        response = self.client.get(reverse('order_list'))
        self.assertContains(response, 'Products (View)')
        self.assertContains(response, 'Suppliers (View)')
        self.assertNotContains(response, 'Purchase Orders')
        self.assertNotContains(response, 'Reports')

    def test_sidebar_links_for_inventory_manager(self):
        manager = User.objects.create_user(
            username="manager_route_test",
            password="StrongPass123!",
            role=User.ROLE_INVENTORY_MANAGER,
        )
        self.client.force_login(manager)
        response = self.client.get(reverse('product_list'))
        self.assertContains(response, 'Purchase Orders')
        self.assertNotContains(response, 'Reports')
        
class RoleBasedLoginViewTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="test_customer",
            password="testpass123",
            role=User.ROLE_CUSTOMER,
        )

        self.sales_rep = User.objects.create_user(
            username="test_sales_rep",
            password="testpass123",
            role=User.ROLE_SALES_REP,
        )

    def test_customer_cannot_login_to_staff_portal(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "test_customer",
                "password": "testpass123",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Customer accounts cannot access the staff portal.",
        )

        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sales_rep_can_still_login(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "test_sales_rep",
                "password": "testpass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("order_create"))

        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_authenticated_customer_cannot_access_login_page(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Customer accounts cannot access the staff portal.",
        )

        self.assertNotIn("_auth_user_id", self.client.session)


class ReportsAccessRestrictionTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='password123',
            role=User.ROLE_ADMIN,
        )
        self.staff_user = User.objects.create_user(
            username='staff_test',
            password='password123',
            role=getattr(User, 'ROLE_STAFF', 'STAFF'),
        )
        self.sales_rep_user = User.objects.create_user(
            username='sales_test',
            password='password123',
            role=User.ROLE_SALES_REP,
        )
        self.reports_url = reverse('reports')

    def test_admin_can_access_reports(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_access_reports_returns_403(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 403)

    def test_sales_rep_cannot_access_reports_returns_403(self):
        self.client.force_login(self.sales_rep_user)
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 302)

    def test_unreleased_reports_and_invoices_nav_links_are_hidden_for_all_roles(self):
        for user in (
            self.admin_user,
            self.staff_user,
            self.sales_rep_user,
        ):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("dashboard"))

                self.assertNotContains(response, ">Reports<", html=False)
                self.assertNotContains(response, ">Invoices<", html=False)
                self.assertNotContains(response, ">Executive Reports<", html=False)


class RevenueCalculationTests(TestCase):

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="revenue_admin",
            password="password123",
            role=User.ROLE_ADMIN,
        )

        self.client.force_login(self.admin_user)
        self.dashboard_url = reverse("dashboard")
        self.reports_url = reverse("reports")

    def create_order(self, status=Order.STATUS_PENDING, total_amount=Decimal("100.00"), created_at=None ):
        order = Order.objects.create(
            user=self.admin_user,
            customer_name="Test Customer",
            total_amount=total_amount,
            status=status,
        )

        if created_at is not None:
            Order.objects.filter(pk=order.pk).update(
                created_at=created_at
            )
            order.refresh_from_db()

        return order

    def test_dashboard_revenue_includes_completed_orders(self):
        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("100.00"),
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_revenue"], Decimal("100.00"))

    def test_dashboard_revenue_excludes_pending_orders(self):
        self.create_order(
            status=Order.STATUS_PENDING,
            total_amount=Decimal("100.00"),
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_revenue"], Decimal("0"))

    def test_dashboard_revenue_updates_when_order_is_completed_and_cancelled(self):
        order = self.create_order(
            status=Order.STATUS_PENDING,
            total_amount=Decimal("100.00"),
        )

        # Pending order should not count as revenue.
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total_revenue"],
            Decimal("0"),
        )

        # Complete the order.
        order.mark_completed()
        order.refresh_from_db()

        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total_revenue"],
            Decimal("100.00"),
        )

        # Cancel the completed order.
        order.cancel()
        order.refresh_from_db()

        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total_revenue"],
            Decimal("0"),
        )

    def test_dashboard_revenue_only_sums_completed_orders(self):
        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("100.00"),
        )

        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("50.00"),
        )

        self.create_order(
            status=Order.STATUS_CANCELLED,
            total_amount=Decimal("75.00"),
        )

        self.create_order(
            status=Order.STATUS_PENDING,
            total_amount=Decimal("25.00"),
        )

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total_revenue"],
            Decimal("150.00"),
        )

    def test_monthly_revenue_includes_completed_orders(self):
        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("100.00"),
        )

        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(len(monthly_revenue), 1)
        self.assertEqual(
            monthly_revenue[0]["total"],
            Decimal("100.00"),
        )

    def test_monthly_revenue_excludes_cancelled_orders(self):
        self.create_order(
            status=Order.STATUS_CANCELLED,
            total_amount=Decimal("100.00"),
        )

        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(monthly_revenue, [])

    def test_monthly_revenue_updates_when_order_is_completed_and_cancelled(self):
        order = self.create_order(
            status=Order.STATUS_PENDING,
            total_amount=Decimal("100.00"),
        )

        # Pending order should not appear in revenue.
        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(monthly_revenue, [])

        # Complete the order.
        order.mark_completed()
        order.refresh_from_db()

        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(len(monthly_revenue), 1)
        self.assertEqual(
            monthly_revenue[0]["total"],
            Decimal("100.00"),
        )

        # Cancel the completed order.
        order.cancel()
        order.refresh_from_db()

        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(
            monthly_revenue,
            [],
        )
        
    def test_monthly_revenue_only_sums_completed_orders(self):
        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("100.00"),
        )

        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("50.00"),
        )

        self.create_order(
            status=Order.STATUS_CANCELLED,
            total_amount=Decimal("25.00"),
        )

        self.create_order(
            status=Order.STATUS_PENDING,
            total_amount=Decimal("75.00"),
        )

        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(len(monthly_revenue), 1)
        self.assertEqual(
            monthly_revenue[0]["total"],
            Decimal("150.00"),
        )

    def test_monthly_revenue_is_grouped_by_month(self):
        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("100.00"),
            created_at=timezone.datetime(
                2026,
                1,
                15,
                tzinfo=timezone.get_current_timezone(),
            ),
        )

        self.create_order(
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal("200.00"),
            created_at=timezone.datetime(
                2026,
                2,
                15,
                tzinfo=timezone.get_current_timezone(),
            ),
        )

        response = self.client.get(self.reports_url)
        self.assertEqual(response.status_code, 200)
        monthly_revenue = list(response.context["monthly_revenue"])

        self.assertEqual(len(monthly_revenue), 2)
        self.assertEqual(
            monthly_revenue[0]["total"],
            Decimal("100.00"),
        )
        self.assertEqual(
            monthly_revenue[1]["total"],
            Decimal("200.00"),
        )
class DashboardRevenueChartTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='chart_admin',
            password='password123',
            role='ADMIN',
        )
        self.client.force_login(self.admin)
        self.dashboard_url = reverse('dashboard')

    def test_completed_orders_appear_in_dashboard_chart_data(self):
        Order.objects.create(
            user=self.admin,
            customer_name='Chart Customer',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('500.00'),
        )

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('revenue_chart_labels', response.context)
        self.assertIn('revenue_chart_values', response.context)
        self.assertTrue(len(response.context['revenue_chart_labels']) >= 1)
        self.assertIn(500.0, response.context['revenue_chart_values'])

    def test_pending_and_cancelled_orders_are_excluded(self):
        Order.objects.create(
            user=self.admin,
            customer_name='Pending Customer',
            status=Order.STATUS_PENDING,
            total_amount=Decimal('300.00'),
        )
        Order.objects.create(
            user=self.admin,
            customer_name='Cancelled Customer',
            status=Order.STATUS_CANCELLED,
            total_amount=Decimal('999.00'),
        )

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['revenue_chart_values'], [])

    def test_monthly_labels_and_totals_are_correct(self):
        order_jan_1 = Order.objects.create(
            user=self.admin,
            customer_name='Jan Customer 1',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('100.00'),
        )
        Order.objects.filter(pk=order_jan_1.pk).update(
            created_at=timezone.datetime(2026, 1, 15, tzinfo=timezone.get_current_timezone())
        )

        order_jan_2 = Order.objects.create(
            user=self.admin,
            customer_name='Jan Customer 2',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('150.00'),
        )
        Order.objects.filter(pk=order_jan_2.pk).update(
            created_at=timezone.datetime(2026, 1, 15, tzinfo=timezone.get_current_timezone())
        )

        order_feb = Order.objects.create(
            user=self.admin,
            customer_name='Feb Customer',
            status=Order.STATUS_COMPLETED,
            total_amount=Decimal('200.00'),
        )
        Order.objects.filter(pk=order_feb.pk).update(
            created_at=timezone.datetime(2026, 2, 15, tzinfo=timezone.get_current_timezone())
        )

        response = self.client.get(self.dashboard_url)
        labels = response.context['revenue_chart_labels']
        values = response.context['revenue_chart_values']

        self.assertEqual(len(labels), 2)
        self.assertEqual(values[0], 250.0)
        self.assertEqual(values[1], 200.0)

    def test_empty_revenue_data_is_handled_safely(self):
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['revenue_chart_labels'], [])
        self.assertEqual(response.context['revenue_chart_values'], [])
        self.assertContains(response, 'No revenue data yet')
        self.assertNotContains(response, 'chart.js@4.4.0')

class RouteProtectionTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username="protection_admin",
            password="password123",
            role=User.ROLE_ADMIN,
        )

        self.customer = User.objects.create_user(
            username="protection_customer",
            password="password123",
            role=User.ROLE_CUSTOMER,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('login')}?next={reverse('product_list')}",
        )

    def test_anonymous_user_can_access_login_page(self):
        response = self.client.get(reverse("login"))

        self.assertNotEqual(response.status_code, 302)

    def test_authenticated_admin_can_access_products(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)

    def test_authenticated_customer_is_forbidden_from_products(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 403)
