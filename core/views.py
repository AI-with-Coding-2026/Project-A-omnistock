from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.urls import reverse
from django.db.models import F, Sum

from inventory.models import Product, Supplier
from orders.models import Order, OrderItem

from .forms import StyledLoginForm
from .models import User
from .utils import admin_required, staff_or_admin_required


class RoleBasedLoginView(LoginView):
    template_name = 'core/login.html'
    authentication_form = StyledLoginForm
    redirect_authenticated_user = True
    
    CUSTOMER_ACCESS_MESSAGE = "Customer accounts cannot access the staff portal."

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == User.ROLE_CUSTOMER:
            from django.contrib.auth import logout
            logout(request)
            return self.render_to_response(
                self.get_context_data(
                    customer_access_error=self.CUSTOMER_ACCESS_MESSAGE
                )
            )

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        if user.role == User.ROLE_CUSTOMER:
            context = self.get_context_data(
                form=form,
                customer_access_error=self.CUSTOMER_ACCESS_MESSAGE,
            )
            return self.render_to_response(context)

        return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        if user.role == User.ROLE_ADMIN:
            return reverse('dashboard')
        elif user.role == User.ROLE_INVENTORY_MANAGER:
            return reverse('product_list')
        elif user.role == User.ROLE_SALES_REP:
            return reverse('order_create')
        else:
            return reverse('dashboard')


class RoleBasedLogoutView(LogoutView):
    next_page = "/login/"


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
        total_revenue=Sum("total_amount")
    )["total_revenue"] or 0

    products = Product.objects.select_related('supplier').all()
    low_stock = Product.low_stock()
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


@admin_required
def reports(request):
    """Reports & Analytics page"""
    from django.db.models.functions import TruncMonth

    monthly_revenue = (
        Order.objects.filter(status=Order.STATUS_COMPLETED)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )
    
    top_products = (
        OrderItem.objects
        .filter(order__status=Order.STATUS_COMPLETED)
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )

    return render(request, 'core/reports.html', {
        'title': 'Executive Reports',
        'is_admin': True,
        'top_products': top_products,
        'monthly_revenue': monthly_revenue,
    })
