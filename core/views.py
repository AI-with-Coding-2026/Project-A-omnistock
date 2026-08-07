from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.urls import reverse

from inventory.models import Product

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
    products = Product.objects.select_related('supplier').all()
    low_stock = [p for p in products if p.is_low_stock]
    is_admin = request.user.role == User.ROLE_ADMIN

    context = {
        'user': request.user,
        'is_admin': is_admin,
        'low_stock': low_stock,
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

