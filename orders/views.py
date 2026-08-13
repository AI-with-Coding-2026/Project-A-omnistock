from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import admin_required, staff_or_admin_required

from .forms import OrderForm
from .models import Order

from django.db.models import F
from inventory.models import Product 

ORDER_CANCEL_REDIRECT = 'order_list'

@staff_or_admin_required
def order_list(request):
    orders = Order.objects.select_related('user').all()
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'is_admin': request.user.role == 'ADMIN',
    })


@staff_or_admin_required
@transaction.atomic
def order_create(request):
    form = OrderForm(request.POST or None)
    if form.is_valid():
        order = form.save(commit=False)
        order.user = request.user
        order.save()
        messages.success(request, 'Order created.')
        return redirect('order_list')
    return render(request, 'orders/order_form.html', {
        'form': form,
        'title': 'Create Order',
    })


@admin_required
@transaction.atomic
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if order.status == Order.STATUS_CANCELLED:
        messages.warning(request, 'This order is already cancelled.')
        return redirect(ORDER_CANCEL_REDIRECT)

    for item in order.items.all():
        Product.objects.filter(id=item.product_id).update(
            stock_quantity=F('stock_quantity') + item.quantity
        )

    order.status = Order.STATUS_CANCELLED
    order.save(update_fields=['status'])

    messages.success(request, 'Order cancelled and stock restored.')
    return redirect(ORDER_CANCEL_REDIRECT)

@staff_or_admin_required
def invoice_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'orders/invoice.html', {'order': order})
