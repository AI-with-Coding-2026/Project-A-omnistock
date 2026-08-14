from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import admin_required, staff_or_admin_required
from inventory.models import Product

from .forms import OrderForm
from .models import Order, OrderItem

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
<<<<<<< HEAD
    products = list(Product.objects.values('id', 'name', 'sku', 'unit_price'))
=======
    products = list(
        Product.objects.values(
            'id',
            'name',
            'sku',
            'unit_price',
            'stock_quantity',
        )
    )

>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
    form = OrderForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        product_ids = request.POST.getlist('items[][product]')
        quantities = request.POST.getlist('items[][quantity]')

<<<<<<< HEAD
        # ── VALIDATE EVERYTHING BEFORE TOUCHING THE DATABASE ──
        valid_items = []
=======
        # ---------------------------------------------------------
        # STEP 1: PARSE LINE ITEMS + AGGREGATE FOR STOCK VALIDATION
        # ---------------------------------------------------------
        requested_quantities = defaultdict(int)
        line_items = []
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
        has_error = False

        for product_id, qty in zip(product_ids, quantities):
            if not product_id or not qty:
                continue

            try:
                quantity = int(qty)
            except ValueError:
<<<<<<< HEAD
                form.add_error(None, 'Quantity must be a valid whole number.')
=======
                form.add_error(
                    None,
                    'Quantity must be a valid whole number.'
                )
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
                has_error = True
                break

            if quantity <= 0:
<<<<<<< HEAD
                form.add_error(None, 'Quantity must be greater than zero.')
                has_error = True
                break

            # NEW: Confirm the product exists BEFORE we create the order
            try:
                product = Product.objects.get(pk=product_id)
            except Product.DoesNotExist:
                from django.http import Http404
                raise Http404(f"Product {product_id} does not exist.")

            valid_items.append((product, quantity))
=======
                form.add_error(
                    None,
                    'Quantity must be greater than zero.'
                )
                has_error = True
                break

            requested_quantities[product_id] += quantity
            line_items.append((product_id, quantity))
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32

        if has_error:
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

<<<<<<< HEAD
        if not valid_items:
            form.add_error(None, 'At least one valid line item is required.')
=======
        if not line_items:
            form.add_error(
                None,
                'At least one valid line item is required.'
            )

>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

<<<<<<< HEAD
        # ── ALL VALID: NOW CREATE ORDER + ITEMS ──
=======
        # ---------------------------------------------------------
        # STEP 2: LOCK PRODUCTS + VALIDATE COMBINED QUANTITY
        # ---------------------------------------------------------
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
                    f'Available: {product.stock_quantity}.'
                )
                has_error = True
                break

        if has_error:
            return render(request, 'orders/order_form.html', {
                'form': form,
                'title': 'Create Order',
                'products': products,
            })

        # ---------------------------------------------------------
        # STEP 3: CREATE ORDER
        # ---------------------------------------------------------
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
        order = form.save(commit=False)
        order.user = request.user
        order.save()

        total = 0
<<<<<<< HEAD
        for product, quantity in valid_items:
=======

        # ---------------------------------------------------------
        # STEP 4: CREATE ORIGINAL ORDER ITEMS + DEDUCT STOCK
        # ---------------------------------------------------------
        for product_id, quantity in line_items:
            product = locked_products[product_id]

>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
<<<<<<< HEAD
                unit_price=product.unit_price,  # Always from DB
            )
            total += product.unit_price * quantity

=======
                unit_price=product.unit_price,
            )

            # -----------------------------------------------------
            # STEP 5: ATOMIC STOCK DEDUCTION
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
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
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
<<<<<<< HEAD
    order = get_object_or_404(
        Order.objects.select_for_update(),
        pk=pk
    )
=======
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
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32

    if order.status == Order.STATUS_CANCELLED:
        messages.warning(request, 'This order is already cancelled.')
        return redirect(ORDER_CANCEL_REDIRECT)

    if order.status != Order.STATUS_COMPLETED:
        messages.warning(
            request,
            'Only completed orders can be cancelled.'
        )
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
<<<<<<< HEAD
    return render(request, 'orders/invoice.html', {'order': order})
=======

    return render(request, 'orders/invoice.html', {
        'order': order,
    })
>>>>>>> 14cd080b9ba57419f80a3e674673e089f7429e32
