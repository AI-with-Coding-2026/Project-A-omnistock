from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_ADMIN = 'ADMIN'
    ROLE_CUSTOMER = 'CUSTOMER'
    ROLE_INVENTORY_MANAGER = 'INVENTORY_MANAGER'
    ROLE_SALES_REP = 'SALES_REP'
    ROLE_STAFF = 'STAFF'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_INVENTORY_MANAGER, 'Inventory Manager'),
        (ROLE_SALES_REP, 'Sales Rep'),
        (ROLE_STAFF, 'Staff'),
    ]

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=ROLE_STAFF,
    )

    def save(self, *args, **kwargs):
        # Admin gets superuser access; staff-type roles get staff access.
        if self.role == self.ROLE_ADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role in (
            self.ROLE_STAFF,
            self.ROLE_INVENTORY_MANAGER,
            self.ROLE_SALES_REP,
        ):
            self.is_staff = True
            self.is_superuser = False
        else:
            self.is_staff = False
            self.is_superuser = False
        super().save(*args, **kwargs)
