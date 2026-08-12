from django.contrib import messages
from django.db import IntegrityError
from django.db.models import F, BooleanField, Case, When, Value
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import (
    admin_or_inventory_manager_required,
    admin_required,
    staff_or_admin_required,
)

from .forms import ProductForm, SupplierForm
from .models import Product, Supplier


@staff_or_admin_required
def product_list(request):
    products = Product.objects.select_related('supplier').all()
    low_stock = [p for p in products if p.is_low_stock]
    return render(request, 'inventory/product_list.html', {
        'products': products,
        'low_stock': low_stock,
        'is_admin': request.user.role == 'ADMIN',
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
        product.delete()
        messages.success(request, 'Product deleted.')
        return redirect('product_list')
    return render(request, 'inventory/product_confirm_delete.html', {'object': product})


@staff_or_admin_required  # All staff roles can VIEW the supplier list (including Sales Rep)
def supplier_list(request):
    """
    Supplier index page - read-only view accessible by all staff roles.
    Sales Rep can view but not create/edit (buttons hidden via can_manage_suppliers).
    """
    role = request.user.role
    suppliers = Supplier.objects.prefetch_related('products').all()
    return render(request, 'inventory/supplier_list.html', {
        'suppliers': suppliers,
        'is_admin': role == 'ADMIN',  # Used to show/hide Delete button (Admin only)
        'can_manage_suppliers': role in ('ADMIN', 'INVENTORY_MANAGER'),  # Controls Create/Edit button visibility
    })


@admin_or_inventory_manager_required  # Only Admin and Inventory Manager can create suppliers
def supplier_create(request):
    """
    Create new supplier. Enforces role-based access at the view level.
    Sales Rep attempting direct URL access will get 403 PermissionDenied.

    IntegrityError handling provides defense-in-depth for email uniqueness
    (form validation is primary, DB constraint is backstop).
    """
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                # DB-level uniqueness violation (e.g., race condition or direct DB insert)
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


@admin_or_inventory_manager_required  # Only Admin and Inventory Manager can edit suppliers
def supplier_edit(request, pk):
    """
    Edit existing supplier. Enforces role-based access at the view level.
    Sales Rep attempting direct URL access will get 403 PermissionDenied.

    ModelForm handles allowing unchanged email (same instance) while rejecting
    another supplier's email. IntegrityError provides DB-level protection.
    """
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                # Catches attempt to use another supplier's email
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


@admin_required  # Only Admin role can delete suppliers (not Inventory Manager)
def supplier_delete(request, pk):
    """
    Delete supplier. Most restrictive access - Admin only.
    Inventory Manager is blocked from this operation.
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.delete()
        messages.success(request, 'Supplier deleted.')
        return redirect('supplier_index')
    return render(request, 'inventory/supplier_confirm_delete.html', {'object': supplier})
