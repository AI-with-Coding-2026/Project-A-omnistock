from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
import uuid


class InvalidPurchaseOrderTransitionError(ValidationError):
    """Raised when an invalid purchase order status transition is attempted."""
    pass


def generate_po_number():
    return f'PO-{uuid.uuid4().hex[:10].upper()}'


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=False , null=False)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='products',
    )
    sku = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'

    def save(self, *args, **kwargs):
        if not self.sku:
            random_suffix = uuid.uuid4().hex[:6].upper()
            self.sku = f'SUP-PROD-{random_suffix}'
        super().save(*args, **kwargs)

    @classmethod
    def low_stock(cls):
        return cls.objects.filter(
            stock_quantity__lte=F('reorder_level')
        )


class PurchaseOrder(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_RECEIVED = 'received'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_RECEIVED, 'Received'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    VALID_TRANSITIONS = {
        STATUS_PENDING: {STATUS_APPROVED, STATUS_CANCELLED},
        STATUS_APPROVED: {STATUS_RECEIVED, STATUS_CANCELLED},
        STATUS_RECEIVED: set(),
        STATUS_CANCELLED: set(),
    }

    po_number = models.CharField(max_length=50, unique=True, default=generate_po_number)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.po_number} — {self.supplier.name}'

    def can_approve(self):
        return self.status == self.STATUS_PENDING

    def can_receive(self):
        return self.status == self.STATUS_APPROVED

    def can_cancel(self):
        return self.status in [self.STATUS_PENDING, self.STATUS_APPROVED]

    def can_transition_to(self, target_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, set())
        return target_status in allowed

    def _stored_status(self):
        if not self.pk:
            return None
        stored = PurchaseOrder.objects.filter(pk=self.pk).values('status').first()
        return stored['status'] if stored else None

    def _assert_valid_transition(self, from_status, to_status):
        if from_status == to_status:
            return
        if to_status not in self.VALID_TRANSITIONS.get(from_status, set()):
            raise InvalidPurchaseOrderTransitionError(
                f"Cannot transition purchase order from '{from_status}' to '{to_status}'."
            )

    def approve(self, save=True):
        if not self.can_approve():
            raise InvalidPurchaseOrderTransitionError(
                f"Cannot transition purchase order #{self.pk or self.po_number} "
                f"from '{self.status}' to '{self.STATUS_APPROVED}'."
            )
        self.status = self.STATUS_APPROVED
        if save:
            self.save(update_fields=['status', 'updated_at'])

    def mark_received(self, save=True):
        if not self.can_receive():
            raise InvalidPurchaseOrderTransitionError(
                f"Cannot transition purchase order #{self.pk or self.po_number} "
                f"from '{self.status}' to '{self.STATUS_RECEIVED}'."
            )
        self.status = self.STATUS_RECEIVED
        if save:
            self.save(update_fields=['status', 'updated_at'])

    def cancel(self, save=True):
        if not self.can_cancel():
            raise InvalidPurchaseOrderTransitionError(
                f"Cannot transition purchase order #{self.pk or self.po_number} "
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
        stored_status = self._stored_status()
        if stored_status is not None:
            self._assert_valid_transition(stored_status, self.status)
        super().save(*args, **kwargs)


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    def line_total(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return f'{self.product.name} x{self.quantity} ({self.purchase_order.po_number})'

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_cost < 0:
            raise ValidationError({'unit_cost': 'Unit cost must be 0 or greater.'})