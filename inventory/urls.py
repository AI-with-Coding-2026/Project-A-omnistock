from django.urls import path
from . import views

urlpatterns = [
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/index/', views.product_index, name='product_index'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),

    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/index/', views.supplier_list, name='supplier_index'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),
]