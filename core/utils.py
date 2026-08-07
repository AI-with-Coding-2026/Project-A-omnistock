from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    """Allow only authenticated users whose role is ADMIN."""
    @login_required
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) != 'ADMIN':
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
