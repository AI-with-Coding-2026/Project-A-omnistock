from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
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
    """Allow any authenticated staff-type or admin user."""
    return user_passes_test(
        lambda u: u.is_authenticated and getattr(u, 'role', None) in [
            'ADMIN', 'STAFF', 'INVENTORY_MANAGER', 'SALES_REP'
        ]
    )(view_func)
