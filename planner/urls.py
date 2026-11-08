from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views, api_views

urlpatterns = [
    path("help/", views.help_page, name="help"),
    path("trips/<int:pk>/api/<str:provider>/", api_views.trip_api, name="trip_api"),
    path("trips/<int:pk>/location/", api_views.select_destination, name="select_destination"),
    path("trips/<int:pk>/photos/", api_views.photo_upload, name="photo_upload"),
    path("photos/<int:pk>/delete/", api_views.photo_delete, name="photo_delete"),
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.CustomerLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("my-trips/", views.dashboard, name="dashboard"),
    path("trips/new/", views.trip_form, name="trip_create"),
    path("trips/<int:pk>/", views.trip_detail, name="trip_detail"),
    path("trips/<int:pk>/edit/", views.trip_form, name="trip_edit"),
    path("trips/<int:pk>/delete/", views.trip_delete, name="trip_delete"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),
]
