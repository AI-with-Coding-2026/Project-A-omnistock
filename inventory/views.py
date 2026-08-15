from django.contrib import messages
from django.db.models import F, BooleanField, Case, When, Value, Count, Q
from django.shortcuts import get_object_or_404, redirect, render


from core.utils import admin_required, staff_or_admin_required

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


@staff_or_admin_required
def supplier_list(request):
    q = request.GET.get('q', '').strip()
    suppliers = Supplier.objects.annotate(product_count=Count('products'))

    if q:
        suppliers = suppliers.filter(
            Q(name__icontains=q) | Q(email__icontains=q)
        )

    return render(request, 'inventory/supplier_list.html', {
        'suppliers': suppliers,
        'q': q,
        'is_admin': request.user.role == 'ADMIN',
    })


@admin_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Supplier created.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_form.html', {
        'form': form,
        'title': 'Create Supplier',
    })


@admin_required
def supplier_update(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    form = SupplierForm(request.POST or None, instance=supplier)
    if form.is_valid():
        form.save()
        messages.success(request, 'Supplier updated.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_form.html', {
        'form': form,
        'title': 'Update Supplier',
    })


@admin_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.delete()
        messages.success(request, 'Supplier deleted.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_confirm_delete.html', {'object': supplier})