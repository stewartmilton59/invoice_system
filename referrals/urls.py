from django.urls import path
from . import views

app_name = 'referral'

urlpatterns = [
    # Dashboard
    path('', views.referral_dashboard, name='dashboard'),
    
    # Sources CRUD
    path('sources/', views.referral_source_list, name='source_list'),
    path('sources/add/', views.referral_source_add, name='source_add'),
    path('sources/<int:pk>/edit/', views.referral_source_edit, name='source_edit'),
    path('sources/<int:pk>/delete/', views.referral_source_delete, name='source_delete'),
    
    # Invoices CRUD
    path('invoices/', views.referral_invoice_list, name='invoice_list'),
    path('invoices/add/', views.referral_invoice_add, name='invoice_add'),
    path('invoices/<int:pk>/', views.referral_invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.referral_invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.referral_invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/payment/', views.referral_invoice_update_payment, name='update_payment'),
    
    # PDF & Exports
    path('invoices/<int:pk>/pdf/', views.generate_referral_invoice_pdf, name='generate_referral_invoice_pdf'),
    path('invoices/export/excel/', views.export_referral_invoices_excel, name='export_excel'),
    path('invoices/export/pdf/', views.export_referral_invoices_pdf, name='export_pdf'),
    
    # Utilities
    path('invoices/clear-filters/', views.clear_referral_filters, name='clear_filters'),
]