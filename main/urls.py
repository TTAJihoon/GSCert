from django.urls import path
from .views import login_test_view
from . import views

urlpatterns = [
    path('welcome/', views.welcome, name='welcome'),
    path('test-login/', login_test_view),
]
