from django.urls import path
from . import views
urlpatterns = [
    path("", views.order_list, name="order_list"),
    path("index/", views.order_index, name="order_index"),
    path("create/", views.order_create, name="order_create"),
    path("<int:pk>/", views.order_detail, name="order_detail"),
    path("<int:pk>/complete/", views.order_complete, name="order_complete"),
    path("<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("<int:pk>/invoice/", views.invoice_view, name="invoice_view"),
    path("<int:order_id>/invoice/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("export/csv/", views.export_orders_csv, name="export_orders_csv"),
]