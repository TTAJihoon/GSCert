from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from main.views.init import index, similar, security, prdinfo, genspark, test

from main.views.testing.history import history
from main.views.testing.similar_summary import summarize_document
from main.views.testing.security import invicti_parse_view

from main.views.testing.history_ECMbtn import start_job, job_status

from main.views.certy.prdinfo_generate import generate_prdinfo
from main.views.certy.prdinfo_URL import source_excel_view
from main.views.certy.prdinfo_download import download_filled_prdinfo

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('index/', index, name='index'),
    path('', RedirectView.as_view(url='/index/', permanent=False)),
    
    path('history/', history, name='history'),
    path('similar/', similar, name='similar'),
    path('summarize_document/', summarize_document, name='summarize_document'),
    path('security/', security, name='security'),
    path('security/invicti/parse/', invicti_parse_view, name='invicti_parse'),
    
    # RQ 대시보드 (작업 큐 모니터링)
    path("django-rq/", include("django_rq.urls")),
    # API: 작업 생성 / 상태 조회
    path("api/run-job/", start_job, name="start_job"),
    path("api/job/<uuid:job_id>/", job_status, name="job_status"),

    path('prdinfo/', prdinfo, name='prdinfo'),
    path('generate_prdinfo/', generate_prdinfo, name='generate_prdinfo'),
    path('source-excel/', source_excel_view, name='source-excel'),
    path("download-filled/", download_filled_prdinfo, name="download_filled"),
    
    path('genspark/', genspark, name='genspark'),
    path('test/', test, name='genspark2'),
]
