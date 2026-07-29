from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('', views.home, name='home'),
    path('search/', views.search_route, name='search_route'),
    path('book/<int:trip_id>/', views.book_ticket_step_1, name='book_ticket_step_1'),
    path('verify-otp/', views.verify_otp_step_2, name='verify_otp_step_2'),
    path('success/<str:pnr>/', views.booking_success, name='booking_success'),
    path('track/', views.track_booking, name='track_booking'),
    path('cancel/<str:pnr>/', views.cancel_booking_passenger, name='cancel_booking_passenger'),
    # Employee
    path('employee/login/', views.user_login, name='login'),
    path('employee/dashboard/', views.dashboard_view, name='dashboard'),
    path('employee/logout/', views.user_logout, name='logout'),
    path('employee/bookings/', views.view_bookings, name='view_bookings'),
    path('employee/edit/<int:ticket_id>/', views.edit_ticket, name='edit_ticket'),
    path('employee/delete/<int:ticket_id>/', views.delete_ticket, name='delete_ticket'),
]