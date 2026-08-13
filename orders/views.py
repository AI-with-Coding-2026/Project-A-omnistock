from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import admin_required, staff_or_admin_required
from inventory.models import Product

from .forms import OrderForm
from .models import Order, OrderItem


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

        # ---------------------------------------------------------
        # STEP 1: VALIDATE LINE ITEMS
        # ---------------------------------------------------------
        valid_items = []
        has_error = False

        for product_id, qty in zip(product_ids, quantities):
            if not product_id or not qty:
                continue

            try:
                quantity = int(qty)
            except ValueError:
                form.add_error(
                    None,
                    'Quantity must be a valid whole number.'
                )
                has_error = True
                break

            if quantity <= 0:
                form.add_error(
                    None,
                    'Quantity must be greater than zero.'
                )
                has_error = True
                break

            # Lock the product row while checking stock.
            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=product_id,
            )

            # -----------------------------------------------------
            # STEP 2: STOCK VALIDATION
            # Task 3.1
            # -----------------------------------------------------
            if quantity > product.stock_quantity:
                form.add_error(
                    None,
                    f'Insufficient stock for {product.name}. '
                    f'Available: {product.stock_quantity}.'
                )
                has_error = True
                break

            valid_items.append((product, quantity))

        if has_error:
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        if not valid_items:
            form.add_error(
                None,
                'At least one valid line item is required.'
            )

            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        # ---------------------------------------------------------
        # STEP 3: CREATE ORDER
        # ---------------------------------------------------------
        order = form.save(commit=False)
        order.user = request.user
        order.save()

        total = 0

        # ---------------------------------------------------------
        # STEP 4: CREATE ORDER ITEMS + DEDUCT STOCK
        # ---------------------------------------------------------
        for product, quantity in valid_items:
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.unit_price,
            )

            # -----------------------------------------------------
            # STEP 5: ATOMIC STOCK DEDUCTION
            # Task 2354
            # -----------------------------------------------------
            Product.objects.filter(
                id=product.id,
            ).update(
                stock_quantity=F('stock_quantity') - quantity
            )

            total += product.unit_price * quantity

        # ---------------------------------------------------------
        # STEP 6: UPDATE ORDER TOTAL
        # ---------------------------------------------------------
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
    order = get_object_or_404(Order, pk=pk)

    if order.status in (
        Order.STATUS_PENDING,
        Order.STATUS_COMPLETED,
    ):
        order.status = Order.STATUS_CANCELLED
        order.save()

        messages.success(request, 'Order cancelled.')
    else:
        messages.warning(
            request,
            'This order cannot be cancelled.'
        )

    return redirect('order_list')


@staff_or_admin_required
def invoice_view(request, pk):
    order = get_object_or_404(Order, pk=pk)

    return render(request, 'orders/invoice.html', {
        'order': order,
    })