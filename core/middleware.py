from django.shortcuts import redirect
from django.urls import reverse


class RoleProtectionMiddleware:
    """
    Redirect anonymous users away from protected sections.

    Role-based access is handled separately by view decorators.
    """

    PROTECTED_PREFIXES = (
        "/inventory/",
        "/orders/",
        "/reports/",
        "/suppliers/",
        "/products/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_protected = request.path.startswith(self.PROTECTED_PREFIXES)

        if is_protected and not request.user.is_authenticated:
            login_url = reverse("login")
            return redirect(f"{login_url}?next={request.path}")

        return self.get_response(request)