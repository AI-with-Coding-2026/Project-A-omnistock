from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import BooleanField, Case, Count, F, ProtectedError, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.utils import (
    admin_or_inventory_manager_required,
    admin_required,
    staff_or_admin_required,
)

from .forms import ProductForm, SupplierForm
from .models import Product, Supplier


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
    products = Product.objects.select_related('supplier').all()
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
    role = request.user.role
    q = request.GET.get('q', '').strip()
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