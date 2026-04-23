from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

name='main'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('district/<int:district_id>/', views.district_detail, name='district_detail'),
    path('facility/<int:facility_id>/', views.facility_detail, name='facility_detail'),
    path('invoices/', views.all_invoices, name='all_invoices'),
    path('update-payment/<int:invoice_id>/', views.update_payment, name='update_payment'),
    path('export/excel/', views.export_to_excel, name='export_excel'),
    path('export/pdf/', views.export_to_pdf, name='export_pdf'),
    path('login/', views.custom_login, name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', views.custom_logout, name='logout'),

    # Data entry URLs (staff only)
    path('districts/', views.district_list, name='district_list'),
    path('districts/add/', views.add_district, name='add_district'),
    path('districts/edit/<int:district_id>/', views.edit_district, name='edit_district'),
    path('districts/delete/<int:district_id>/', views.delete_district, name='delete_district'),

    path('facilities/', views.facility_list, name='facility_list'),
    path('facilities/add/', views.add_facility, name='add_facility'),
    path('facilities/edit/<int:facility_id>/', views.edit_facility, name='edit_facility'),
    path('facilities/delete/<int:facility_id>/', views.delete_facility, name='delete_facility'),

    path('invoices/add/', views.add_invoice, name='add_invoice'),
    path('invoices/delete/<int:invoice_id>/', views.delete_invoice, name='delete_invoice'),

    # Filtered Export URLs
    path('export/filtered/excel/', views.export_filtered_excel, name='export_filtered_excel'),
    path('export/filtered/pdf/', views.export_filtered_pdf, name='export_filtered_pdf'),
    path('clear-filters/', views.clear_filters, name='clear_filters'),

    # Profile URLs
    path('profile/', views.profile_view, name='profile'),
    path('profile/settings/', views.profile_settings, name='profile_settings'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/upload-picture/', views.upload_profile_picture, name='upload_profile_picture'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notification/<int:pk>/', views.notification_detail, name='notification_detail'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/delete-old/', views.delete_old_notifications, name='delete_old_notifications'),
    path('notifications/<int:pk>/delete/', views.delete_notification, name='delete_notification'),
    path('notifications/mark-all-read/', views.mark_all_as_read, name='mark_all_as_read'),
]