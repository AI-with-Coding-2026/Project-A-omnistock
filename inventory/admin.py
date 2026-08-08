from django.contrib import admin

from .models import Product, Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone')
    search_fields = ('name', 'email')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'stock_quantity', 'reorder_level', 'price', 'is_low_stock', 'supplier')
    list_filter = ('supplier',)
    search_fields = ('name', 'sku')
