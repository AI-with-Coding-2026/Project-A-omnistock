def feature_flags(request):
    return {
        "reports_ready": False,
        "invoices_ready": False,
    }