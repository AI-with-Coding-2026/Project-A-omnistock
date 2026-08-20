from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template

from xhtml2pdf import pisa

from core.utils import admin_required, staff_or_admin_required
from inventory.models import Product

from .forms import OrderForm
from .models import Order, OrderItem


ORDER_CANCEL_REDIRECT = 'order_list'


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
def order_detail(request, order_id):
    order = get_object_or_404(
    Order.objects.prefetch_related('items__product'),
    pk=order_id,
    )
    return render(request, 'orders/order_detail.html', {
        'order': order
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


@admin_required
@transaction.atomic
def order_cancel(request, pk):
    order = get_object_or_404(
        Order.objects.select_for_update(),
        pk=pk,
    )

    if order.status == Order.STATUS_CANCELLED:
        messages.warning(request, 'This order is already cancelled.')
        return redirect(ORDER_CANCEL_REDIRECT)

    if order.status != Order.STATUS_COMPLETED:
        messages.warning(
            request,
            'Only completed orders can be cancelled.',
        )
        return redirect(ORDER_CANCEL_REDIRECT)

    for item in order.items.all():
        Product.objects.filter(id=item.product_id).update(
            stock_quantity=F('stock_quantity') + item.quantity,
        )

    order.status = Order.STATUS_CANCELLED
    order.save(update_fields=['status'])

    messages.success(request, 'Order cancelled and stock restored.')
    return redirect(ORDER_CANCEL_REDIRECT)


@staff_or_admin_required
def invoice_view(request, pk):
    order = get_object_or_404(Order, pk=pk)

    return render(request, 'orders/invoice.html', {
        'order': order,
    })

def render_html_to_pdf(html):
    response = HttpResponse(content_type='application/pdf')
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return None
    return response 

@staff_or_admin_required
def invoice_pdf(request, pk):
    order = get_object_or_404(Order, pk=pk)
    template = get_template('orders/invoice_pdf.html')
    html = template.render({'order': order})
    pdf_response = render_html_to_pdf(html)
    if pdf_response is None:
        return HttpResponse('Error generating PDF', status=500)
    pdf_response['Content-Disposition'] = f'attachment; filename="invoice_{order.order_number}.pdf"'
    return pdf_response