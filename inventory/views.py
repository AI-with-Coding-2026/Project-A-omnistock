from django.db.models import Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.paginator import Paginator #Added

from core.utils import admin_required, staff_or_admin_required

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

@staff_or_admin_required  #Added
def product_index(request):
    q = request.GET.get('q', '')
    supplier_id = request.GET.get('supplier')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    products = Product.objects.all()
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q))
    if supplier_id:
        products = products.filter(supplier_id=supplier_id)
    if min_price:
        products = products.filter(unit_price__gte=min_price)
    if max_price:
        products = products.filter(unit_price__lte=max_price)
    suppliers = Supplier.objects.all()

    paginator = Paginator(products, 20) #Added
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'inventory/product_index.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'q': q,
        'suppliers': suppliers,
        'selected_supplier': supplier_id,
        'min_price': min_price,
        'max_price': max_price,
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
    suppliers = Supplier.objects.prefetch_related('products').all()
    return render(request, 'inventory/supplier_list.html', {
        'suppliers': suppliers,
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
