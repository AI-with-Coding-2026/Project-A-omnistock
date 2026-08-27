import math

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, Count, F, ProtectedError, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.utils import (
    admin_or_inventory_manager_required,
    admin_required,
    staff_or_admin_required,
)

from .forms import ProductForm, SupplierForm
from .models import InvalidPurchaseOrderTransitionError, Product, PurchaseOrder, PurchaseOrderItem, Supplier


@staff_or_admin_required
def product_list(request):
    products = Product.objects.select_related('supplier').annotate(
        is_low_stock=Case(
            When(
                stock_quantity__lte=F('reorder_level'),
                then=Value(True)
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
    )

    low_stock = products.filter(is_low_stock=True)

    return render(request, 'inventory/product_list.html', {
        'products': products,
        'low_stock': low_stock,
        'is_admin': request.user.role == 'ADMIN',
    })


@staff_or_admin_required
def product_index(request):
    q = request.GET.get('q', '')
    supplier_id = request.GET.get('supplier')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    products = Product.objects.select_related('supplier').annotate(
        is_low_stock=Case(
            When(
                stock_quantity__lte=F('reorder_level'),
                then=Value(True)
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
    )
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q))
    if supplier_id:
        products = products.filter(supplier_id=supplier_id)
    if min_price:
        try:
            products = products.filter(unit_price__gte=float(min_price))
        except ValueError:
            messages.error(request, 'Min price must be a number.')
            min_price = ''
    if max_price:
        try:
            products = products.filter(unit_price__lte=float(max_price))
        except ValueError:
            messages.error(request, 'Max price must be a number.')
            max_price = ''

    stock_status = request.GET.get('stock_status', '')
    if stock_status == 'low':
        products = products.filter(is_low_stock=True)
    elif stock_status == 'in_stock':
        products = products.filter(is_low_stock=False)

    suppliers = Supplier.objects.all()

    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    querystring = request.GET.copy()
    querystring.pop('page', None)
    querystring = querystring.urlencode()

    return render(request, 'inventory/product_index.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'q': q,
        'suppliers': suppliers,
        'selected_supplier': supplier_id,
        'min_price': min_price,
        'max_price': max_price,
        'selected_stock_status': stock_status,
        'querystring': querystring,
    })


@admin_required
def product_create(request):
    form = ProductForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Product created.')
        return redirect('product_list')
    return render(request, 'inventory/product_form.html', {
        'form': form,
        'title': 'Create Product',
    })


@admin_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if form.is_valid():
        form.save()
        messages.success(request, 'Product updated.')
        return redirect('product_list')
    return render(request, 'inventory/product_form.html', {
        'form': form,
        'title': 'Update Product',
    })


@admin_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, 'Product deleted.')
        except ProtectedError:
            messages.error(
                request,
                'This product cannot be deleted because it is referenced by existing order history.'
            )
        return redirect('product_list')
    return render(request, 'inventory/product_confirm_delete.html', {'object': product})


@staff_or_admin_required
def supplier_list(request):
    """
    Supplier index page - read-only view accessible by all staff roles.
    Sales Rep can view but not create/edit (buttons hidden via can_manage_suppliers).
    Supports search by name/email and shows product count per supplier.
    """
    q = request.GET.get('q', '').strip()
    role = request.user.role
    suppliers = Supplier.objects.annotate(product_count=Count('products'))

    if q:
        suppliers = suppliers.filter(
            Q(name__icontains=q) | Q(email__icontains=q)
        )

    return render(request, 'inventory/supplier_list.html', {
        'suppliers': suppliers,
        'q': q,
        'is_admin': role == 'ADMIN',
        'can_manage_suppliers': role in ('ADMIN', 'INVENTORY_MANAGER'),
    })


@admin_or_inventory_manager_required
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error('email', 'This email is already in use.')
            else:
                messages.success(request, 'Supplier created.')
                return redirect('supplier_index')
    else:
        form = SupplierForm()

    return render(request, 'inventory/supplier_form.html', {
        'form': form,
        'title': 'Create Supplier',
    })


@admin_or_inventory_manager_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error('email', 'This email is already in use.')
            else:
                messages.success(request, 'Supplier updated.')
                return redirect('supplier_index')
    else:
        form = SupplierForm(instance=supplier)

    return render(request, 'inventory/supplier_form.html', {
        'form': form,
        'title': 'Update Supplier',
    })


@admin_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        try:
            supplier.delete()
            messages.success(request, 'Supplier deleted.')
        except ProtectedError:
            messages.error(
                request,
                'This supplier cannot be deleted because one or more of their products are referenced by existing order history.'
            )
        return redirect('supplier_index')
    return render(request, 'inventory/supplier_confirm_delete.html', {'object': supplier})


@admin_or_inventory_manager_required
def purchase_order_list(request):
    purchase_orders = PurchaseOrder.objects.select_related('supplier', 'created_by').all()
    return render(request, 'inventory/purchase_order_list.html', {
        'purchase_orders': purchase_orders,
        'is_admin': request.user.role == 'ADMIN',
    })


@admin_or_inventory_manager_required
@transaction.atomic
def purchase_order_create(request):
    suppliers = Supplier.objects.all()
    products = list(
        Product.objects.values('id', 'name', 'sku', 'unit_price')
    )

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        product_ids = request.POST.getlist('items[][product]')
        quantities = request.POST.getlist('items[][quantity]')
        unit_costs = request.POST.getlist('items[][unit_cost]')
        new_product_flags = request.POST.getlist('items[][is_new]')
        new_product_names = request.POST.getlist('items[][new_product_name]')
        new_product_prices = request.POST.getlist('items[][new_product_price]')
        new_product_stocks = request.POST.getlist('items[][new_product_stock]')
        new_product_reorders = request.POST.getlist('items[][new_product_reorder]')

        supplier = get_object_or_404(Supplier, pk=supplier_id)
        existing_product_ids = set(Product.objects.values_list('id', flat=True))

        validated_items = []
        has_error = False

        for idx, (product_id, qty, unit_cost) in enumerate(zip(product_ids, quantities, unit_costs)):
            is_new = idx < len(new_product_flags) and new_product_flags[idx] == 'on'
            if not product_id and not is_new:
                continue

            try:
                quantity = int(qty)
            except (ValueError, TypeError):
                messages.error(request, 'Quantity must be a valid whole number.')
                has_error = True
                break

            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero.')
                has_error = True
                break

            try:
                cost = float(unit_cost)
                if math.isnan(cost) or math.isinf(cost):
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, 'Unit cost must be a valid numeric price.')
                has_error = True
                break

            if cost < 0:
                messages.error(request, 'Unit cost must be 0 or greater.')
                has_error = True
                break

            if is_new:
                name = new_product_names[idx].strip() if idx < len(new_product_names) else ''
                name = name.replace('\x00', '')
                if not name:
                    messages.error(request, 'New product name is required.')
                    has_error = True
                    break

                if len(name) > 255:
                    messages.error(request, 'Product name cannot exceed 255 characters.')
                    has_error = True
                    break

                try:
                    price = float(new_product_prices[idx]) if idx < len(new_product_prices) else 0.0
                    if math.isnan(price) or math.isinf(price):
                        raise ValueError
                except (ValueError, TypeError):
                    messages.error(request, 'New product unit price must be a valid number.')
                    has_error = True
                    break

                if price < 0:
                    messages.error(request, 'New product unit price must be 0 or greater.')
                    has_error = True
                    break

                try:
                    raw_stock = new_product_stocks[idx] if idx < len(new_product_stocks) else ''
                    stock = int(raw_stock) if raw_stock else 0
                except (ValueError, TypeError):
                    messages.error(request, 'New product stock quantity must be a valid whole number.')
                    has_error = True
                    break

                if stock < 0:
                    messages.error(request, 'New product stock quantity cannot be negative.')
                    has_error = True
                    break

                try:
                    raw_reorder = new_product_reorders[idx] if idx < len(new_product_reorders) else ''
                    reorder = int(raw_reorder) if raw_reorder else 0
                except (ValueError, TypeError):
                    messages.error(request, 'New product reorder level must be a valid whole number.')
                    has_error = True
                    break

                if reorder < 0:
                    messages.error(request, 'New product reorder level cannot be negative.')
                    has_error = True
                    break

                validated_items.append({
                    'is_new': True,
                    'name': name,
                    'price': price,
                    'stock': stock,
                    'reorder': reorder,
                    'quantity': quantity,
                    'unit_cost': cost,
                })
            else:
                try:
                    pid = int(product_id)
                except (ValueError, TypeError):
                    messages.error(request, 'Invalid product selection.')
                    has_error = True
                    break

                if pid not in existing_product_ids:
                    messages.error(request, f'Selected product ID #{pid} does not exist.')
                    has_error = True
                    break

                validated_items.append({
                    'is_new': False,
                    'product_id': pid,
                    'quantity': quantity,
                    'unit_cost': cost,
                })

        if has_error or not validated_items:
            if not has_error and not validated_items:
                messages.error(request, 'At least one line item is required.')
            return render(request, 'inventory/purchase_order_form.html', {
                'suppliers': suppliers,
                'products': products,
                'title': 'Create Purchase Order',
            })

        purchase_order = PurchaseOrder.objects.create(
            supplier=supplier,
            created_by=request.user,
            status=PurchaseOrder.STATUS_PENDING,
        )

        for item_data in validated_items:
            if item_data['is_new']:
                product = Product.objects.create(
                    supplier=supplier,
                    name=item_data['name'],
                    unit_price=item_data['price'],
                    stock_quantity=item_data['stock'],
                    reorder_level=item_data['reorder'],
                )
                product_id = product.id
            else:
                product_id = item_data['product_id']

            PurchaseOrderItem.objects.create(
                purchase_order=purchase_order,
                product_id=product_id,
                quantity=item_data['quantity'],
                unit_cost=item_data['unit_cost'],
            )

        messages.success(request, 'Purchase order created.')
        return redirect('purchase_order_list')

    return render(request, 'inventory/purchase_order_form.html', {
        'suppliers': suppliers,
        'products': products,
        'title': 'Create Purchase Order',
    })
