from django.urls import path
from . import views

urlpatterns = [
    path("", views.login_view, name="login"),
    path('home/', views.home, name='home'),  
    path('trip-map/', views.trip_map, name='trip_map'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('trip/<int:id>/', views.trip_detail, name='trip_detail'),
    path('plan-trip/', views.plan_trip, name='plan_trip'),
    path('generate-trip/', views.generate_trip, name='generate_trip'),
    path('trip-result/', views.trip_result, name='trip_result'),
    path('register/', views.register, name='register'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('add-trip/', views.add_trip, name='add_trip'),
    path('edit-trip/<int:id>/', views.edit_trip, name='edit_trip'),
    path('delete-trip/<int:id>/', views.delete_trip, name='delete_trip'),
    path('add-user/', views.add_user, name='add_user'),
    path('edit-user/<int:id>/', views.edit_user, name='edit_user'),
    path('delete-user/<int:id>/', views.delete_user, name='delete_user'),
    path('add-booking/', views.add_booking, name='add_booking'),
    path('edit-booking/<int:id>/', views.edit_booking, name='edit_booking'),
    path('delete-booking/<int:id>/', views.delete_booking, name='delete_booking'),
    path('book-trip/<int:id>/', views.book_trip, name='book_trip'),
    path('route-history/<int:id>/open/', views.open_route_history, name='open_route_history'),
    path('route-history/<int:id>/edit/', views.edit_route_history, name='edit_route_history'),
    path('route-history/<int:id>/delete/', views.delete_route_history, name='delete_route_history'),
    path('select-option/<int:index>/', views.select_trip_option, name='select_trip_option'),
]

