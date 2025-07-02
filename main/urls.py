from django.contrib.auth import views as auth_views
from django.urls import path
from main.views.init import index, security, genspark, test
from main.views.testing.sendValue import search_history
from main.utils.reload_reference import reload_reference_view

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('index/', index, name='index'),
    path('security/', security, name='security'),
    path('genspark/', genspark, name='genspark'),
    path('test/', test, name='genspark2'),
    path('search-history/', search_history, name='search'),
    path('reload-reference/', reload_reference_view, name='reload_reference'),
    
]
