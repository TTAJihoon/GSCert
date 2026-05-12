from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie

from main.views.download_review_api import (
    active_job as download_review_active_job,
    job_detail as download_review_job_detail,
    job_project_results as download_review_job_project_results,
    job_projects as download_review_job_projects,
    jobs as download_review_jobs,
    projects as download_review_projects,
)


@ensure_csrf_cookie
def download_review(request):
    return render(request, "download_review.html")


urlpatterns = [
    path("", lambda request: redirect("download_review"), name="index"),
    path("history/", lambda request: redirect("download_review"), name="history"),
    path("similar/", lambda request: redirect("download_review"), name="similar"),
    path("security/", lambda request: redirect("download_review"), name="security"),
    path("prdinfo/", lambda request: redirect("download_review"), name="prdinfo"),
    path("checkreport/", lambda request: redirect("download_review"), name="checkreport"),
    path("download-review/", download_review, name="download_review"),
    path("api/projects/", download_review_projects, name="download_review_projects"),
    path("api/jobs/", download_review_jobs, name="download_review_jobs"),
    path("api/jobs/active/", download_review_active_job, name="download_review_active_job"),
    path("api/jobs/<uuid:job_id>/", download_review_job_detail, name="download_review_job_detail"),
    path("api/jobs/<uuid:job_id>/projects/", download_review_job_projects, name="download_review_job_projects"),
    path("api/job-projects/<uuid:job_project_id>/results/", download_review_job_project_results, name="download_review_job_project_results"),
]
