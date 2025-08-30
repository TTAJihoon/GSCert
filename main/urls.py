from django.contrib.auth import views as auth_views
from django.urls import path
from main.views.init import index, similar, security, prdinfo, genspark, test

from main.views.testing.history import history
from main.views.testing.similar_summary import summarize_document

from main.views.certy.prdinfo_generate import generate_prdinfo
from main.views.certy.prdinfo_URL import source_excel_view
from main.views.certy.prdinfo_download import download_filled_prdinfo

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('index/', index, name='index'),
    
    path('history/', history, name='history'),
    path('similar/', similar, name='similar'),
    path('summarize_document/', summarize_document, name='summarize_document'),
    path('security/', security, name='security'),

    path('prdinfo/', prdinfo, name='prdinfo'),
    path('generate_prdinfo/', generate_prdinfo, name='generate_prdinfo'),
    path('source-excel/', source_excel_view, name='source-excel'),
    path("download-filled/", download_filled_prdinfo, name="download_filled"),
    
    path('genspark/', genspark, name='genspark'),
    path('test/', test, name='genspark2'),
]
