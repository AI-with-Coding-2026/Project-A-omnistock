from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.RoleBasedLoginView.as_view(), name='login'),
    path('logout/', views.RoleBasedLogoutView.as_view(), name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('reports/', views.reports, name='reports'),
]