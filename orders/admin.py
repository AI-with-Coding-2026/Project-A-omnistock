from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'product', 'quantity', 'status', 'total', 'created_at')
    list_filter = ('status',)
    search_fields = ('customer_name', 'product__name')
