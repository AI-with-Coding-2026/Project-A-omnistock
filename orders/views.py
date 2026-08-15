# orders/views.py
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import admin_required, staff_or_admin_required

from .forms import OrderForm
from .models import Order


@staff_or_admin_required
def order_list(request):
    orders = Order.objects.select_related('product').all()
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'is_admin': request.user.role == 'ADMIN',
    })


@staff_or_admin_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'orders/order_detail.html', {'order': order})


@staff_or_admin_required
@transaction.atomic
def order_create(request):
    form = OrderForm(request.POST or None)
    if form.is_valid():
        order = form.save(commit=False)
        
        product = order.product.__class__.objects.select_for_update().get(pk=order.product.pk)
        
        if product.stock_quantity < order.quantity:
            form.add_error('quantity', f'Insufficient stock. Available: {product.stock_quantity}')
        else:
            order.status = Order.STATUS_COMPLETED
            order.save()
            
            product.stock_quantity -= order.quantity
            product.save()
            
            messages.success(request, 'Order created and stock deducted.')
            return redirect('order_list')
            
    return render(request, 'orders/order_form.html', {
        'form': form,
        'title': 'Create Order',
    })


@admin_required
@transaction.atomic
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.status == Order.STATUS_COMPLETED:
        product = order.product.__class__.objects.select_for_update().get(pk=order.product.pk)
        
        product.stock_quantity += order.quantity
        product.save()
        
        order.status = Order.STATUS_CANCELLED
        order.save()
        messages.success(request, 'Order cancelled and stock restored.')
    else:
        messages.warning(request, 'Only completed orders can be cancelled.')
        
    return redirect('order_list')


@staff_or_admin_required
def invoice_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'orders/invoice.html', {'order': order})