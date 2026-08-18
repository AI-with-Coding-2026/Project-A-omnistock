import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F


class InvalidOrderTransitionError(ValidationError):
    """Raised when an invalid order status transition is attempted."""
    pass


def generate_order_number():
    return f'ORD-{uuid.uuid4().hex[:10].upper()}'


def generate_invoice_number():
    return f'INV-{uuid.uuid4().hex[:10].upper()}'


class Order(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        STATUS_PENDING: {STATUS_COMPLETED, STATUS_CANCELLED},
        STATUS_COMPLETED: {STATUS_CANCELLED},
        STATUS_CANCELLED: set(),
    }

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order_number = models.CharField(max_length=50, unique=True, default=generate_order_number)
    customer_name = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_number} — {self.customer_name}"

    def can_mark_completed(self):
        return self.status == self.STATUS_PENDING

    def can_cancel(self):
        return self.status in [self.STATUS_PENDING, self.STATUS_COMPLETED]

    def can_transition_to(self, target_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, set())
        return target_status in allowed

    def restore_stock(self):
        """Restores stock quantity for all line items in this order."""
        from inventory.models import Product
        for item in self.items.all():
            Product.objects.filter(id=item.product_id).update(
                stock_quantity=F('stock_quantity') + item.quantity,
            )

    def _stored_status(self):
        """Returns the status currently persisted in the database, or None if unsaved."""
        if not self.pk:
            return None
        stored = Order.objects.filter(pk=self.pk).values('status').first()
        return stored['status'] if stored else None

    def _assert_valid_transition(self, from_status, to_status):
        """Raises InvalidOrderTransitionError if the given transition is not permitted."""
        if from_status == to_status:
            return
        if to_status not in self.VALID_TRANSITIONS.get(from_status, set()):
            raise InvalidOrderTransitionError(
                f"Cannot transition order from '{from_status}' to '{to_status}'."
            )

    def mark_completed(self, save=True):
        """Transitions order from PENDING to COMPLETED."""
        if not self.can_mark_completed():
            raise InvalidOrderTransitionError(
                f"Cannot transition order #{self.pk or self.order_number} "
                f"from '{self.status}' to '{self.STATUS_COMPLETED}'."
            )
        self.status = self.STATUS_COMPLETED
        if save:
            self.save(update_fields=['status', 'updated_at'])

    def cancel(self, save=True):
        """
        Transitions order to CANCELLED.

        Stock restoration for a COMPLETED -> CANCELLED transition is handled by
        save(), so that the stock movement is always committed together with the
        status change and can never be applied without it.
        """
        if not self.can_cancel():
            raise InvalidOrderTransitionError(
                f"Cannot transition order #{self.pk or self.order_number} "
                f"from '{self.status}' to '{self.STATUS_CANCELLED}'."
            )
        self.status = self.STATUS_CANCELLED
        if save:
            self.save(update_fields=['status', 'updated_at'])

    def clean(self):
        super().clean()
        stored_status = self._stored_status()
        if stored_status is not None:
            self._assert_valid_transition(stored_status, self.status)

    def save(self, *args, **kwargs):
        """
        Enforces the status state machine on every write and pairs the
        COMPLETED -> CANCELLED transition with stock restoration atomically.
        """
        stored_status = self._stored_status()

        if stored_status is not None:
            self._assert_valid_transition(stored_status, self.status)

        restores_stock = (
            stored_status == self.STATUS_COMPLETED
            and self.status == self.STATUS_CANCELLED
        )

        with transaction.atomic():
            super().save(*args, **kwargs)
            if restores_stock:
                self.restore_stock()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.product} x{self.quantity} ({self.order.order_number})"


class Invoice(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=50, unique=True, default=generate_invoice_number)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invoice_number
