from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie

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
    local_review_app_download,
    local_review_project_metadata,
    local_review_rules_bundle,
    local_review_rules_manifest,
    projects as download_review_projects,
    rule_result_artifact as download_review_rule_result_artifact,
)


@ensure_csrf_cookie
def download_review(request):
    return render(request, "review/ecm_download_review.html")


def consultation(request):
    return render(request, "consultation.html")


urlpatterns = [
    path("", lambda request: redirect("download_review"), name="index"),
    path("history/", lambda request: redirect("download_review"), name="history"),
    path("similar/", lambda request: redirect("download_review"), name="similar"),
    path("security/", lambda request: redirect("download_review"), name="security"),
    path("consultation", consultation, name="consultation"),
    path("consultation/", consultation, name="consultation_slash"),
    path("prdinfo/", lambda request: redirect("download_review"), name="prdinfo"),
    path("checkreport/", lambda request: redirect("download_review"), name="checkreport"),
    path("download-review/", download_review, name="download_review"),
    path("api/projects/", download_review_projects, name="download_review_projects"),
    path("api/jobs/", download_review_jobs, name="download_review_jobs"),
    path("api/jobs/active/", download_review_active_job, name="download_review_active_job"),
    path("api/jobs/<uuid:job_id>/cancel/", download_review_job_cancel, name="download_review_job_cancel"),
    path("api/jobs/<uuid:job_id>/", download_review_job_detail, name="download_review_job_detail"),
    path("api/jobs/<uuid:job_id>/projects/", download_review_job_projects, name="download_review_job_projects"),
    path("api/jobs/<uuid:job_id>/results.xlsx", download_review_job_results_excel, name="download_review_job_results_excel"),
    path("api/job-projects/<uuid:job_project_id>/results/", download_review_job_project_results, name="download_review_job_project_results"),
    path("api/job-projects/<uuid:job_project_id>/results.xlsx", download_review_job_project_results_excel, name="download_review_job_project_results_excel"),
    path("api/rule-results/<uuid:result_id>/artifacts/<str:artifact_id>/", download_review_rule_result_artifact, name="download_review_rule_result_artifact"),
    path("api/projects/<str:project_number>/latest-results/", download_review_latest_project_results, name="download_review_latest_project_results"),
    path("api/local-review/health/", local_review_health, name="local_review_health"),
    path("api/local-review/app/download/", local_review_app_download, name="local_review_app_download"),
    path("api/local-review/projects/<str:project_number>/metadata/", local_review_project_metadata, name="local_review_project_metadata"),
    path("api/local-review/rules/manifest/", local_review_rules_manifest, name="local_review_rules_manifest"),
    path("api/local-review/rules/bundle/", local_review_rules_bundle, name="local_review_rules_bundle"),
]
