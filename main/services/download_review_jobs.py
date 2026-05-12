import json
import re
from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from main.models import (
    DownloadReviewJob,
    DownloadReviewJobStatus,
    DownloadReviewProject,
    DownloadReviewProjectStatus,
    DownloadReviewProjectReviewStatus,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
from main.services.reference_db import get_projects_by_numbers


PROJECT_NUMBER_RE = re.compile(r"^TTA-\d{2}-\d{5}$")
ACTIVE_JOB_STATUSES = (
    DownloadReviewJobStatus.SCHEDULED,
    DownloadReviewJobStatus.QUEUED,
    DownloadReviewJobStatus.RUNNING,
)
JOB_LIST_PARAM_NAMES = {"status", "limit", "offset"}
JOB_LIST_STATUS_FILTERS = {
    "all": None,
    "finished": (
        DownloadReviewJobStatus.COMPLETED,
        DownloadReviewJobStatus.FAILED,
        DownloadReviewJobStatus.CANCELED,
    ),
    DownloadReviewJobStatus.SCHEDULED: (DownloadReviewJobStatus.SCHEDULED,),
    DownloadReviewJobStatus.QUEUED: (DownloadReviewJobStatus.QUEUED,),
    DownloadReviewJobStatus.RUNNING: (DownloadReviewJobStatus.RUNNING,),
    DownloadReviewJobStatus.COMPLETED: (DownloadReviewJobStatus.COMPLETED,),
    DownloadReviewJobStatus.FAILED: (DownloadReviewJobStatus.FAILED,),
    DownloadReviewJobStatus.CANCELED: (DownloadReviewJobStatus.CANCELED,),
}
DEFAULT_JOB_LIST_LIMIT = 20
MAX_JOB_LIST_LIMIT = 100


class DownloadReviewJobRequestError(ValueError):
    error_code = "invalid_job_request"
    status_code = 400

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}


class DownloadReviewDuplicateProjectError(DownloadReviewJobRequestError):
    error_code = "active_project_conflict"
    status_code = 409


class DownloadReviewQueueFullError(DownloadReviewJobRequestError):
    error_code = "queue_full"
    status_code = 409


class DownloadReviewCompletedProjectError(DownloadReviewJobRequestError):
    error_code = "completed_project_not_allowed"
    status_code = 400


class DownloadReviewNotFoundError(LookupError):
    error_code = "not_found"
    status_code = 404

    def __init__(self, message):
        super().__init__(message)
        self.details = {}


@dataclass(frozen=True)
class JobSchedule:
    status: str
    available_after: object
    queued_at: object


def create_download_review_job(payload, request_ip=None, now=None):
    project_numbers = parse_project_numbers(payload)
    projects = get_projects_by_numbers(project_numbers)
    _validate_projects_found(project_numbers, projects)
    _validate_not_completed(projects)

    workflow_alias = getattr(settings, "WORKFLOW_DATABASE_ALIAS", "workflow")
    with transaction.atomic(using=workflow_alias):
        _validate_active_job_limit()
        _validate_no_active_project(project_numbers)

        schedule = build_job_schedule(now=now)
        job = DownloadReviewJob.objects.create(
            status=schedule.status,
            available_after=schedule.available_after,
            queued_at=schedule.queued_at,
            selected_projects_json=project_numbers,
            requested_project_count=len(project_numbers),
            requested_ip=request_ip,
            progress_message=_initial_progress_message(schedule.status),
        )
        DownloadReviewProject.objects.bulk_create(
            [
                DownloadReviewProject(
                    job=job,
                    project_number=project["project_number"],
                    ecm_row_json=project,
                    status=DownloadReviewProjectStatus.QUEUED,
                )
                for project in projects
            ]
        )

    return {
        "success": True,
        "job_id": str(job.id),
        "status": job.status,
        "status_label": job_status_label(job.status),
        "requested_project_count": job.requested_project_count,
        "available_after": job.available_after.isoformat() if job.available_after else None,
        "message": job_request_message(job.status),
    }


def get_active_job_payload():
    job = find_active_job()
    active_count = DownloadReviewJob.objects.filter(status__in=ACTIVE_JOB_STATUSES).count()
    if job is None:
        return {
            "success": True,
            "active_job": None,
            "active_job_count": 0,
            "polling": {
                "should_poll": False,
                "recommended_interval_ms": None,
                "wake_at": None,
            },
        }

    return {
        "success": True,
        "active_job": serialize_job(job),
        "active_job_count": active_count,
        "polling": polling_hint(job),
    }


def get_jobs_payload(query_params):
    query = parse_job_list_query(query_params)
    qs = DownloadReviewJob.objects.all()
    statuses = JOB_LIST_STATUS_FILTERS[query["status"]]
    if statuses:
        qs = qs.filter(status__in=statuses)

    total = qs.count()
    jobs = qs.order_by("-requested_at", "-id")[query["offset"]:query["offset"] + query["limit"]]
    return {
        "success": True,
        "items": [serialize_job(job) for job in jobs],
        "pagination": {
            "total": total,
            "limit": query["limit"],
            "offset": query["offset"],
            "has_more": query["offset"] + len(jobs) < total,
        },
        "status": query["status"],
    }


def get_job_detail_payload(job_id):
    job = get_job_or_raise(job_id)
    return {
        "success": True,
        "job": serialize_job(job),
        "polling": polling_hint(job),
    }


def get_job_projects_payload(job_id):
    job = get_job_or_raise(job_id)
    projects = job.projects.order_by("created_at", "id")
    return {
        "success": True,
        "job": serialize_job(job),
        "items": [serialize_project(project) for project in projects],
    }


def get_project_results_payload(job_project_id):
    try:
        project = (
            DownloadReviewProject.objects
            .select_related("job")
            .get(id=job_project_id)
        )
    except DownloadReviewProject.DoesNotExist as exc:
        raise DownloadReviewNotFoundError("작업 프로젝트를 찾을 수 없습니다.") from exc

    results = project.rule_results.order_by("sequence", "id")
    return {
        "success": True,
        "job": serialize_job(project.job),
        "project": serialize_project(project),
        "items": [serialize_rule_result(result) for result in results],
    }


def find_active_job():
    running = (
        DownloadReviewJob.objects
        .filter(status=DownloadReviewJobStatus.RUNNING)
        .order_by("started_at", "requested_at", "id")
        .first()
    )
    if running:
        return running

    queued = (
        DownloadReviewJob.objects
        .filter(status=DownloadReviewJobStatus.QUEUED)
        .order_by("queued_at", "requested_at", "id")
        .first()
    )
    if queued:
        return queued

    return (
        DownloadReviewJob.objects
        .filter(status=DownloadReviewJobStatus.SCHEDULED)
        .order_by("available_after", "requested_at", "id")
        .first()
    )


def parse_json_body(request):
    try:
        raw_body = request.body.decode("utf-8") if request.body else "{}"
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownloadReviewJobRequestError("JSON 요청 본문이 올바르지 않습니다.") from exc

    if not isinstance(payload, dict):
        raise DownloadReviewJobRequestError("JSON 요청 본문은 객체여야 합니다.")
    return payload


def parse_job_list_query(query_params):
    unknown = set(query_params.keys()) - JOB_LIST_PARAM_NAMES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise DownloadReviewJobRequestError(f"지원하지 않는 작업 조회 조건입니다: {names}")

    status = str(query_params.get("status") or "all").strip()
    if status not in JOB_LIST_STATUS_FILTERS:
        raise DownloadReviewJobRequestError(f"지원하지 않는 작업 상태 필터입니다: {status}")

    limit = _parse_int(query_params.get("limit"), DEFAULT_JOB_LIST_LIMIT, "limit")
    offset = _parse_int(query_params.get("offset"), 0, "offset")
    if limit < 1 or limit > MAX_JOB_LIST_LIMIT:
        raise DownloadReviewJobRequestError(f"limit은 1부터 {MAX_JOB_LIST_LIMIT} 사이여야 합니다.")
    if offset < 0:
        raise DownloadReviewJobRequestError("offset은 0 이상이어야 합니다.")

    return {
        "status": status,
        "limit": limit,
        "offset": offset,
    }


def parse_project_numbers(payload):
    project_numbers = payload.get("project_numbers")
    if not isinstance(project_numbers, list) or not project_numbers:
        raise DownloadReviewJobRequestError("project_numbers는 1개 이상의 프로젝트번호 배열이어야 합니다.")

    max_projects = getattr(settings, "DOWNLOAD_REVIEW_MAX_PROJECTS_PER_JOB", 100)
    if len(project_numbers) > max_projects:
        raise DownloadReviewJobRequestError(f"한 작업에는 최대 {max_projects}개 프로젝트만 요청할 수 있습니다.")

    normalized = []
    duplicates = []
    seen = set()
    for number in project_numbers:
        value = str(number).strip() if number is not None else ""
        if not PROJECT_NUMBER_RE.match(value):
            raise DownloadReviewJobRequestError(
                "프로젝트번호 형식이 올바르지 않습니다.",
                details={"project_number": value},
            )
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
        normalized.append(value)

    if duplicates:
        raise DownloadReviewJobRequestError(
            "중복된 프로젝트번호가 포함되어 있습니다.",
            details={"duplicates": duplicates},
        )
    return normalized


def build_job_schedule(now=None):
    current = now or timezone.now()
    local_tz = ZoneInfo(getattr(settings, "DOWNLOAD_REVIEW_TIME_ZONE", "Asia/Seoul"))
    local_now = current.astimezone(local_tz)

    if is_start_window(local_now):
        return JobSchedule(
            status=DownloadReviewJobStatus.QUEUED,
            available_after=current,
            queued_at=current,
        )

    next_start_local = local_now.replace(
        hour=getattr(settings, "DOWNLOAD_REVIEW_START_HOUR", 20),
        minute=0,
        second=0,
        microsecond=0,
    )
    if local_now.hour >= getattr(settings, "DOWNLOAD_REVIEW_START_HOUR", 20):
        next_start_local = next_start_local + timedelta(days=1)

    return JobSchedule(
        status=DownloadReviewJobStatus.SCHEDULED,
        available_after=next_start_local.astimezone(datetime_timezone.utc),
        queued_at=None,
    )


def is_start_window(local_time):
    start_hour = getattr(settings, "DOWNLOAD_REVIEW_START_HOUR", 20)
    end_hour = getattr(settings, "DOWNLOAD_REVIEW_END_HOUR", 7)
    hour = local_time.hour
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour


def job_status_label(status):
    labels = {
        DownloadReviewJobStatus.SCHEDULED: "예약됨",
        DownloadReviewJobStatus.QUEUED: "대기중",
        DownloadReviewJobStatus.RUNNING: "진행중",
        DownloadReviewJobStatus.COMPLETED: "완료",
        DownloadReviewJobStatus.FAILED: "실패",
        DownloadReviewJobStatus.CANCELED: "취소",
    }
    return labels.get(status, status)


def project_status_label(status):
    labels = {
        DownloadReviewProjectStatus.QUEUED: "대기중",
        DownloadReviewProjectStatus.RUNNING: "진행중",
        DownloadReviewProjectStatus.DOWNLOADED: "다운로드완료",
        DownloadReviewProjectStatus.INSPECTING: "검사중",
        DownloadReviewProjectStatus.COMPLETED: "완료",
        DownloadReviewProjectStatus.FAILED: "실패",
        DownloadReviewProjectStatus.SKIPPED: "건너뜀",
    }
    return labels.get(status, status)


def review_status_label(status):
    labels = {
        DownloadReviewProjectReviewStatus.UNREVIEWED: "미점검",
        DownloadReviewProjectReviewStatus.COMPLETED: "완료",
        DownloadReviewProjectReviewStatus.NEEDS_FIX: "수정 필요",
        DownloadReviewProjectReviewStatus.HELD: "보류",
    }
    return labels.get(status, status)


def rule_status_label(status):
    labels = {
        DownloadReviewRuleStatus.PASS: "정상",
        DownloadReviewRuleStatus.FAIL: "부적합",
        DownloadReviewRuleStatus.WARNING: "경고",
        DownloadReviewRuleStatus.ERROR: "오류",
    }
    return labels.get(status, status)


def polling_hint(job):
    status = job.status
    if status in (DownloadReviewJobStatus.RUNNING, DownloadReviewJobStatus.QUEUED):
        return {
            "should_poll": True,
            "recommended_interval_ms": 3000,
            "wake_at": None,
        }
    if status == DownloadReviewJobStatus.SCHEDULED:
        return {
            "should_poll": False,
            "recommended_interval_ms": None,
            "wake_at": _iso(job.available_after),
        }
    return {
        "should_poll": False,
        "recommended_interval_ms": None,
        "wake_at": None,
    }


def job_request_message(status):
    if status == DownloadReviewJobStatus.SCHEDULED:
        return "작업 요청이 예약되었습니다. 시작 가능 시간이 되면 요청 순서대로 진행합니다."
    return "작업 요청이 대기열에 등록되었습니다. 요청 순서대로 진행합니다."


def get_job_or_raise(job_id):
    try:
        return DownloadReviewJob.objects.get(id=job_id)
    except DownloadReviewJob.DoesNotExist as exc:
        raise DownloadReviewNotFoundError("작업을 찾을 수 없습니다.") from exc


def serialize_job(job):
    total = job.requested_project_count or job.projects.count()
    completed = job.completed_project_count
    failed = job.failed_project_count
    progress_percent = int(((completed + failed) / total) * 100) if total else 0
    return {
        "id": str(job.id),
        "status": job.status,
        "status_label": job_status_label(job.status),
        "requested_at": _iso(job.requested_at),
        "queued_at": _iso(job.queued_at),
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "canceled_at": _iso(job.canceled_at),
        "available_after": _iso(job.available_after),
        "progress_message": job.progress_message,
        "requested_project_count": total,
        "completed_project_count": completed,
        "failed_project_count": failed,
        "progress_percent": progress_percent,
        "selected_project_numbers": job.selected_projects_json or [],
        "last_error_message": job.last_error_message,
        "worker": {
            "pid": job.worker_pid,
            "host": job.worker_host,
            "heartbeat_at": _iso(job.worker_heartbeat_at),
        },
    }


def serialize_project(project):
    ecm_row = project.ecm_row_json or {}
    return {
        "id": str(project.id),
        "job_id": str(project.job_id),
        "project_number": project.project_number,
        "cert_date": ecm_row.get("cert_date", ""),
        "company": ecm_row.get("company", ""),
        "product": ecm_row.get("product", ""),
        "pl": ecm_row.get("pl", ""),
        "status": project.status,
        "status_label": project_status_label(project.status),
        "review_status": project.review_status,
        "review_status_label": review_status_label(project.review_status),
        "current_step": project.current_step,
        "error_message": project.error_message,
        "error_detail": project.error_detail,
        "retry_count": project.retry_count,
        "zip_file_name": project.zip_file_name,
        "download_dir": _display_path(project.download_dir, project.project_number),
        "started_at": _iso(project.started_at),
        "completed_at": _iso(project.completed_at),
    }


def serialize_rule_result(result):
    return {
        "id": str(result.id),
        "job_project_id": str(result.job_project_id),
        "rule_id": str(result.rule_id) if result.rule_id else None,
        "rule_code": result.rule_code,
        "rule_name": result.rule_name,
        "sequence": result.sequence,
        "file_path": result.file_path,
        "file_name": result.file_name,
        "status": result.status,
        "status_label": rule_status_label(result.status),
        "expected": result.expected,
        "actual": result.actual,
        "message": result.message,
        "raw_detail": result.raw_detail_json or {},
        "created_at": _iso(result.created_at),
    }


def _validate_projects_found(project_numbers, projects):
    missing = [
        project_number
        for project_number, project in zip(project_numbers, projects)
        if project is None
    ]
    if missing:
        raise DownloadReviewJobRequestError(
            "ecmlist.db에서 찾을 수 없는 프로젝트번호가 포함되어 있습니다.",
            details={"missing_project_numbers": missing},
        )


def _validate_not_completed(projects):
    completed = [
        project["project_number"]
        for project in projects
        if project.get("review") == "완료"
    ]
    if completed:
        raise DownloadReviewCompletedProjectError(
            "이미 점검 완료된 프로젝트는 작업 요청할 수 없습니다.",
            details={"completed_project_numbers": completed},
        )


def _validate_active_job_limit():
    active_limit = getattr(settings, "DOWNLOAD_REVIEW_ACTIVE_JOB_LIMIT", 5)
    active_count = DownloadReviewJob.objects.filter(status__in=ACTIVE_JOB_STATUSES).count()
    if active_count >= active_limit:
        raise DownloadReviewQueueFullError(
            f"등록 가능한 작업 수({active_limit}개)를 초과했습니다.",
            details={"active_job_count": active_count, "active_job_limit": active_limit},
        )


def _validate_no_active_project(project_numbers):
    conflicts = list(
        DownloadReviewProject.objects.filter(
            project_number__in=project_numbers,
            job__status__in=ACTIVE_JOB_STATUSES,
        )
        .select_related("job")
        .values("project_number", "job_id", "job__status")
        .order_by("project_number")
    )
    if conflicts:
        raise DownloadReviewDuplicateProjectError(
            "이미 예약됨, 대기중 또는 진행중인 프로젝트가 포함되어 있습니다.",
            details={
                "conflicts": [
                    {
                        "project_number": item["project_number"],
                        "job_id": str(item["job_id"]),
                        "job_status": item["job__status"],
                        "job_status_label": job_status_label(item["job__status"]),
                    }
                    for item in conflicts
                ]
            },
        )


def _initial_progress_message(status):
    if status == DownloadReviewJobStatus.SCHEDULED:
        return "시작 가능 시간까지 예약됨"
    return "대기열 등록 완료"


def _iso(value):
    if not value:
        return None
    return value.isoformat()


def _display_path(path, project_number):
    if not path:
        return ""
    normalized = str(path).replace("\\", "/")
    marker = project_number
    index = normalized.find(marker)
    if index >= 0:
        return normalized[index:]
    return ""


def _parse_int(value, default, name):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DownloadReviewJobRequestError(f"{name}은 숫자여야 합니다.") from exc
