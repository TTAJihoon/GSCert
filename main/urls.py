from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from main.views.init import index, similar, security, prdinfo, checkreport, test, download_review

from main.views.testing.history import history
from main.views.testing.similar_summary import summarize_document
from main.views.testing.security import invicti_parse_view
from main.views.testing.security_GPT import get_gpt_recommendation_view, stream_gpt_recommendation_view

from main.views.certy.prdinfo_generate import generate_prdinfo
from main.views.certy.prdinfo_URL import source_excel_view
from main.views.certy.prdinfo_download import download_filled_prdinfo
from main.views.certy.prdinfo_db import lookup_cert_info

from main.views.review.checkreport import parse_view
from main.views.review.ecm_download_review_api import (
    active_job as download_review_active_job,
    job_cancel as download_review_job_cancel,
    job_detail as download_review_job_detail,
    job_project_results as download_review_job_project_results,
    job_project_results_excel as download_review_job_project_results_excel,
    job_projects as download_review_job_projects,
    job_results_excel as download_review_job_results_excel,
    jobs as download_review_jobs,
    latest_project_results as download_review_latest_project_results,
    local_review_health,
    local_review_project_metadata,
    local_review_rules_bundle,
    local_review_rules_manifest,
    projects as download_review_projects,
    rule_result_artifact as download_review_rule_result_artifact,
)

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('index/', index, name='index'),
    path('', RedirectView.as_view(url='/index/', permanent=False)),
    
    path('history/', history, name='history'),
    path('similar/', similar, name='similar'),
    path('summarize_document/', summarize_document, name='summarize_document'),
    path('security/', security, name='security'),
    path('security/invicti/parse/', invicti_parse_view, name='invicti_parse'),
    path('security/gpt/recommend/', get_gpt_recommendation_view, name='gpt_recommend'),
    path('security/gpt/recommend/stream/', stream_gpt_recommendation_view, name='gpt_recommend_stream'),

    path('prdinfo/', prdinfo, name='prdinfo'),
    path('lookup_cert_info/', lookup_cert_info, name='lookup_cert_info'),
    path('generate_prdinfo/', generate_prdinfo, name='generate_prdinfo'),
    path('source-excel/', source_excel_view, name='source-excel'),
    path("download-filled/", download_filled_prdinfo, name="download_filled"),
    
    path('checkreport/', checkreport, name='checkreport'),
    path("parse/", parse_view, name="parse_view"),
    path('download-review/', download_review, name='download_review'),
    path('api/projects/', download_review_projects, name='download_review_projects'),
    path('api/jobs/', download_review_jobs, name='download_review_jobs'),
    path('api/jobs/active/', download_review_active_job, name='download_review_active_job'),
    path('api/jobs/<uuid:job_id>/cancel/', download_review_job_cancel, name='download_review_job_cancel'),
    path('api/jobs/<uuid:job_id>/', download_review_job_detail, name='download_review_job_detail'),
    path('api/jobs/<uuid:job_id>/projects/', download_review_job_projects, name='download_review_job_projects'),
    path('api/jobs/<uuid:job_id>/results.xlsx', download_review_job_results_excel, name='download_review_job_results_excel'),
    path('api/job-projects/<uuid:job_project_id>/results/', download_review_job_project_results, name='download_review_job_project_results'),
    path('api/job-projects/<uuid:job_project_id>/results.xlsx', download_review_job_project_results_excel, name='download_review_job_project_results_excel'),
    path('api/rule-results/<uuid:result_id>/artifacts/<str:artifact_id>/', download_review_rule_result_artifact, name='download_review_rule_result_artifact'),
    path('api/projects/<str:project_number>/latest-results/', download_review_latest_project_results, name='download_review_latest_project_results'),
    path('api/local-review/health/', local_review_health, name='local_review_health'),
    path('api/local-review/projects/<str:project_number>/metadata/', local_review_project_metadata, name='local_review_project_metadata'),
    path('api/local-review/rules/manifest/', local_review_rules_manifest, name='local_review_rules_manifest'),
    path('api/local-review/rules/bundle/', local_review_rules_bundle, name='local_review_rules_bundle'),
]
