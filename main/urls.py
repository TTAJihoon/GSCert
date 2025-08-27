from django.contrib.auth import views as auth_views
from django.urls import path
from main.views.init import index, similar, security, prdinfo, genspark, test
from main.views.testing.history import history
from main.views.testing.similar_summary import summarize_document

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('index/', index, name='index'),
    
    path('history/', history, name='history'),
    path('similar/', similar, name='similar'),
    path('summarize_document/', summarize_document, name='summarize_document'),
    path('security/', security, name='security'),

    path('prdinfo/', prdinfo, name='prdinfo'),
    
    path('genspark/', genspark, name='genspark'),
    path('test/', test, name='genspark2'),
]
