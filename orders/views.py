import csv
import logging
from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from core.utils import admin_required, staff_or_admin_required
from inventory.models import Product

from .forms import OrderForm
from .models import InvalidOrderTransitionError, Order, OrderItem
from .pdf import render_html_to_pdf

logger = logging.getLogger(__name__)

ORDER_CANCEL_REDIRECT = 'order_list'



@admin_required
def export_orders_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Order #',
        'Customer',
        'Sales Rep',
        'Total',
        'Status',
        'Created At',
    ])

    orders = Order.objects.filter(
        status=Order.STATUS_COMPLETED,
    ).select_related('user')
    for order in orders:
        writer.writerow([
            order.order_number,
            order.customer_name,
            order.user.username,
            order.total_amount,
            order.status,
            order.created_at.isoformat(),
        ])

    return response


@staff_or_admin_required
def order_list(request):
    orders = Order.objects.select_related('user').prefetch_related('items__product').all()
    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'is_admin': request.user.role == 'ADMIN',
    })


@staff_or_admin_required
def order_index(request):
    status = request.GET.get('status')
    customer = request.GET.get('customer')
    orders = Order.objects.select_related('user').order_by('-created_at')
    if status:
        orders = orders.filter(status=status)
    if customer:
        orders = orders.filter(customer_name__icontains=customer)
    return render(request, 'orders/order_index.html', {
        'orders': orders,
        'status_choices': Order.STATUS_CHOICES,
        'status': status,
        'customer': customer,
    })

@staff_or_admin_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product'),
        pk=pk,
    )
    return render(request, 'orders/order_detail.html', {
        'order': order,
        'is_admin': request.user.role == 'ADMIN',
    })

@staff_or_admin_required
@transaction.atomic
def order_create(request):
    products = list(
        Product.objects.values(
            'id',
            'name',
            'sku',
            'unit_price',
            'stock_quantity',
        )
    )

    form = OrderForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        product_ids = request.POST.getlist('items[][product]')
        quantities = request.POST.getlist('items[][quantity]')

        requested_quantities = defaultdict(int)
        line_items = []
        has_error = False

        for product_id, qty in zip(product_ids, quantities):
            if not product_id or not qty:
                continue

            try:
                quantity = int(qty)
            except ValueError:
                form.add_error(
                    None,
                    'Quantity must be a valid whole number.',
                )
                has_error = True
                break

            if quantity <= 0:
                form.add_error(
                    None,
                    'Quantity must be greater than zero.',
                )
                has_error = True
                break

            requested_quantities[product_id] += quantity
            line_items.append((product_id, quantity))

        if has_error:
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        if not line_items:
            form.add_error(
                None,
                'At least one valid line item is required.',
            )
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        locked_products = {}

        for product_id, total_quantity in requested_quantities.items():
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            locked_products[product_id] = product

            if total_quantity > product.stock_quantity:
                form.add_error(
                    None,
                    f'Insufficient stock for {product.name}. '
                    f'Requested: {total_quantity}, '
                    f'Available: {product.stock_quantity}.',
                )
                has_error = True
                break

        if has_error:
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        order = form.save(commit=False)
        order.user = request.user
        order.save()

        total = 0

        for product_id, quantity in line_items:
            product = locked_products[product_id]

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.unit_price,
            )

            Product.objects.filter(
                id=product.id,
            ).update(
                stock_quantity=F('stock_quantity') - quantity,
            )

            total += product.unit_price * quantity

        order.total_amount = total
        order.save()

        messages.success(request, 'Order created.')
        return redirect('order_list')

    return render(request, 'orders/order_form.html', {
        'form': form,
        'title': 'Create Order',
        'products': products,
    })


@staff_or_admin_required
@require_POST
@transaction.atomic
def order_complete(request, pk):
    order = get_object_or_404(
        Order.objects.select_for_update(),
        pk=pk,
    )

    if not order.can_mark_completed():
        logger.warning(
            "Invalid status transition attempted: Cannot mark Order #%s as completed from status '%s' (User: %s)",
            order.pk,
            order.status,
            request.user,
        )
        messages.warning(
            request,
            f"Order #{order.pk} cannot be marked as completed from its current status '{order.get_status_display()}'.",
        )
        return redirect('order_list')

    try:
        order.mark_completed()
        messages.success(request, f"Order #{order.pk} has been marked as completed.")
    except InvalidOrderTransitionError as e:
        logger.error("Error completing order #%s: %s", order.pk, str(e))
        messages.error(request, str(e))

    return redirect('order_list')


@admin_required
@require_POST
@transaction.atomic
def order_cancel(request, pk):
    order = get_object_or_404(
        Order.objects.select_for_update(),
        pk=pk,
    )

    if not order.can_cancel():
        logger.warning(
            "Invalid status transition attempted: Cannot cancel Order #%s from status '%s' (User: %s)",
            order.pk,
            order.status,
            request.user,
        )
        messages.warning(
            request,
            f"This order cannot be cancelled from its current status '{order.get_status_display()}'.",
        )
        return redirect(ORDER_CANCEL_REDIRECT)

    try:
        order.cancel()
        messages.success(request, 'Order cancelled and stock restored.')
    except InvalidOrderTransitionError as e:
        logger.error("Error cancelling order #%s: %s", order.pk, str(e))
        messages.error(request, str(e))

    return redirect(ORDER_CANCEL_REDIRECT)


@staff_or_admin_required
def invoice_view(request, pk):
    order = get_object_or_404(Order, pk=pk)

    return render(request, 'orders/invoice.html', {
        'order': order,
    })


@staff_or_admin_required
def invoice_pdf(request, order_id):
    order = get_object_or_404(Order, pk=order_id)

    html = render_to_string('orders/invoice_pdf.html', {'order': order}, request=request)
    pdf_bytes = render_html_to_pdf(html)

    if not pdf_bytes:
        logger.error("Failed to generate PDF for Order #%s", order.pk)
        messages.error(
            request,
            'Sorry, the invoice PDF could not be generated. Please try again.',
        )
        return redirect('invoice_view', pk=order.pk)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="invoice_{order.order_number}.pdf"'
    )
    return response