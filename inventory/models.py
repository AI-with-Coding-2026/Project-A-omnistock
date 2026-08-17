from django.db import models
from django.db.models import F
import uuid

class Supplier(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=True)
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