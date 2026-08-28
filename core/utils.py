from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied

# Roles that can perform inventory management operations (create/edit suppliers, products)
ADMIN_OR_INVENTORY_MANAGER_ROLES = ('ADMIN', 'INVENTORY_MANAGER')


def admin_required(view_func):
    """
    Decorator that restricts access to Admin role only.
    Used for destructive operations like deleting suppliers/products.
    Raises PermissionDenied (403) if user is not Admin.
    """
    @login_required
    @wraps(view_func)  # Preserves the original function's metadata (name, docstring, etc.)
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) != 'ADMIN':
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped

def admin_or_inventory_manager_required(view_func):
    """
    Decorator that allows both Admin and Inventory Manager roles.
    Used for supplier/product create and edit operations.
    Sales Rep users are blocked with PermissionDenied (403).
    """
    @login_required
    @wraps(view_func)  # Preserves the original function's metadata
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) not in ADMIN_OR_INVENTORY_MANAGER_ROLES:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped

def staff_or_admin_required(view_func):
    """Allow authenticated staff-type or admin users."""

    def check_role(user):
        if not user.is_authenticated:
            return False

        return getattr(user, 'role', None) in [
            'ADMIN',
            'STAFF',
            'INVENTORY_MANAGER',
            'SALES_REP',
        ]

    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            from django.urls import reverse

            login_url = reverse('login')
            return redirect(f'{login_url}?next={request.path}')

        if not check_role(request.user):
            raise PermissionDenied

        return view_func(request, *args, **kwargs)

    return wrapped_view

def supplier_required(view_func):
    """
    Decorator that restricts access to Supplier role only.
    Used for the Supplier Portal PO response view.
    Raises PermissionDenied (403) if user is not a Supplier.
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) != 'SUPPLIER':
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped 

def admin_or_sales_rep_required(view_func):
    """
    Decorator that allows both Admin and Sales Rep roles.
    Used for Customer CRUD — Inventory Managers are blocked (403).
    """
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) not in ('ADMIN', 'SALES_REP'):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped