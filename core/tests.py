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