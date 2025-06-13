from django.contrib.auth import views as auth_views
from django.urls import path
from main.views.login import login_test_view
from main.views.login import welcome
from main.views.login import index
from main.views.sendValue import chat_gpt
from . import views

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='main/registration/login.html'), name='login'),
    path('welcome/', welcome),
    path('index/', index),
    path('test-login/', login_test_view),
    path('chatbot/', chat_gpt, name='llama_test'),
]
