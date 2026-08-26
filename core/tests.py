from django.test import TestCase
from django.urls import reverse

from .models import User


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

    def test_reports_nav_link_is_visible_to_admin_only(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'href="/reports/"')
        self.assertContains(response, 'Reports')

        for user in (self.staff_user, self.sales_rep_user):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("dashboard"))
                self.assertNotContains(response, 'href="/reports/"')
                self.assertNotContains(response, ">Invoices<", html=False)
                self.assertNotContains(response, ">Executive Reports<", html=False)