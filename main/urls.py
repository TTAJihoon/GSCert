from django.contrib.auth import views as auth_views
from django.urls import path
from main.views.login import login_test_view
from . import views

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='main/registration/login.html'), name='login'),
    path('welcome/', views.welcome, name='welcome'),
    path('index/', views.index, name='index'),
    path('test-login/', login_test_view),
]
