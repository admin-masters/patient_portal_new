from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_doctor, name="register"),
    path("modify/<str:doctor_id>/", views.modify_clinic_details, name="modify_clinic_details"),
    path("login/", views.doctor_login, name="login"),
    path("logout/", views.doctor_logout, name="logout"),
    path("request-password-reset/", views.request_password_reset, name="request_password_reset"),
    path("reset/<uidb64>/<token>/", views.password_reset, name="password_reset"),
]
