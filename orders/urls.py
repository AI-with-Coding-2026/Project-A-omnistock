from django.urls import path

from . import views

urlpatterns = [
    path('', views.order_list, name='order_list'),
    path('create/', views.order_create, name='order_create'),
    path('<int:pk>/cancel/', views.order_cancel, name='order_cancel'),
    path('<int:pk>/invoice/', views.invoice_view, name='invoice_view'),
]
