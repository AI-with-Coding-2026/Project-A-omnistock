from django.urls import path
from . import views

urlpatterns = [
    path('', views.RoleBasedLoginView.as_view(), name='login'),
    path('logout/', views.RoleBasedLogoutView.as_view(), name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/', views.reports_view, name='reports'),
]