from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('district/<int:district_id>/', views.district_detail, name='district_detail'),
    path('facility/<int:facility_id>/', views.facility_detail, name='facility_detail'),
    path('invoices/', views.all_invoices, name='all_invoices'),
]
