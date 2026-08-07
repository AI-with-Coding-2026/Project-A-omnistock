from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.urls import reverse
from django.db.models import F, Sum

from inventory.models import Product, Supplier
from orders.models import Order

from .models import User
from .utils import staff_or_admin_required


class RoleBasedLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse('dashboard')


class RoleBasedLogoutView(LogoutView):
    next_page = 'login'


@staff_or_admin_required
def dashboard(request):
    product_count = Product.objects.count()
    supplier_count = Supplier.objects.count()

    low_stock_count = Product.objects.filter(
        stock_quantity__lte=F("reorder_level")
    ).count()

    total_revenue = Order.objects.filter(
        status=Order.STATUS_COMPLETED
    ).aggregate(
        total_revenue=Sum("total")
    )["total_revenue"] or 0

    products = Product.objects.select_related('supplier').all()
    low_stock = [p for p in products if p.is_low_stock]
    is_admin = request.user.role == User.ROLE_ADMIN

    context = {
        'user': request.user,
        'is_admin': is_admin,
        'low_stock': low_stock,
        "product_count": product_count,
        "supplier_count": supplier_count,
        "low_stock_count": low_stock_count,
        "total_revenue": total_revenue,
    }

    if request.user.role == User.ROLE_ADMIN:
        context['title'] = 'Admin Dashboard'
        context['description'] = 'Full access to inventory, suppliers, orders, and user management.'
    elif request.user.role == User.ROLE_INVENTORY_MANAGER:
        context['title'] = 'Inventory Manager Dashboard'
        context['description'] = 'View inventory and suppliers; create orders.'
    elif request.user.role == User.ROLE_SALES_REP:
        context['title'] = 'Sales Rep Dashboard'
        context['description'] = 'Create orders and view invoices.'
    else:
        context['title'] = 'Staff Dashboard'
        context['description'] = 'View inventory and create orders.'

    return render(request, 'core/dashboard.html', context)

