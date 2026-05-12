import os
import socket
import time
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from main.models import (
    DownloadReviewJob,
    DownloadReviewJobStatus,
    DownloadReviewLock,
    DownloadReviewLog,
    DownloadReviewLogLevel,
    DownloadReviewProject,
    DownloadReviewProjectReviewStatus,
    DownloadReviewProjectStatus,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
from main.services.reference_db import ARTIFACT_REVIEW_COLUMNS, write_project_review_result
from main.services.agent_popup import (
    PopupResult,
    handle_folder_popup_and_download,
)
from main.services.download_verify import (
    verify_downloaded_files,
    summarize_files,
)
from main.services.ecm_download import (
    DownloadStepResult,
    close_browser,
    launch_browser,
    run_ecm_automation,
)


DRY_RUN_RULES = [
    "프로젝트번호 파일명 포함",
    "zip 파일 손상 여부",
    "최상위 폴더 구조",
    "시험성적서 PDF 존재",
    "계약서 존재",
    "SW저작권확인서 존재",
    "신청서 존재",
    "제품설명서 존재",
    "시험환경 정보 존재",
    "버전명 일치",
    "회사명 일치",
    "제품명 일치",
    "인증일자 표기",
    "시험PL 표기",
    "결과보고서 표지 값",
    "결과보고서 표 값",
    "Excel 머리글 프로젝트번호",
    "Word 표 프로젝트번호",
    "첨부파일 수정일자",
    "빈 파일 여부",
    "중복 파일명 여부",
    "파일명 특수문자",
    "필수 디렉터리 존재",
    "PDF 텍스트 추출 가능",
    "DOCX XML 파싱 가능",
    "엑셀 시트명 확인",
    "보안 관련 산출물 존재",
    "검토 대상 제외 파일",
    "압축 내 경로 길이",
    "최종 산출물 개수",
]


@dataclass(frozen=True)
class WorkerRunResult:
    processed: bool
    job_id: str | None = None
    status: str = "idle"
    message: str = ""


def run_worker_once(*, dry_run=False, sleep_seconds=0, headless=True):
    if not dry_run:
        return _run_live_worker(headless=headless)

    claim = claim_next_job()
    if claim is None:
        return WorkerRunResult(
            processed=False,
            status="idle",
            message="시작 가능한 작업이 없습니다.",
        )

    job = claim
    try:
        run_dry_run_job(job, sleep_seconds=sleep_seconds)
        return WorkerRunResult(
            processed=True,
            job_id=str(job.id),
            status="completed",
            message="dry-run 작업을 완료했습니다.",
        )
    except Exception as exc:
        mark_job_failed(job, str(exc))
        return WorkerRunResult(
            processed=True,
            job_id=str(job.id),
            status="failed",
            message=str(exc),
        )
    finally:
        release_worker_lock(job)



def _run_live_worker(*, headless=True):
    """실제 ECM 자동화를 사용하는 worker 실행."""
    import asyncio

    claim = claim_next_job()
    if claim is None:
        return WorkerRunResult(
            processed=False,
            status="idle",
            message="시작 가능한 작업이 없습니다.",
        )

    job = claim
    try:
        asyncio.run(_run_live_job(job, headless=headless))
        return WorkerRunResult(
            processed=True,
            job_id=str(job.id),
            status="completed",
            message="ECM 다운로드 자동화 작업을 완료했습니다.",
        )
    except Exception as exc:
        mark_job_failed(job, str(exc))
        return WorkerRunResult(
            processed=True,
            job_id=str(job.id),
            status="failed",
            message=str(exc),
        )
    finally:
        release_worker_lock(job)


async def _run_live_job(job, *, headless=True):
    """작업 단위로 browser를 launch/close하고 프로젝트를 순차 처리한다.

    각 프로젝트에 대해:
    1. ECM 웹페이지1에서 프로젝트 폴더 선택 → 전체 선택 → 다운로드 메뉴 클릭 (5~6단계)
    2. Windows 폴더 찾아보기 팝업에서 다운로드 폴더 선택 (7단계)
    3. 전송현황 창 대기 및 시스템 알림 처리 (8단계)
    """
    browser = await launch_browser(headless=headless)
    try:
        projects = list(job.projects.order_by("created_at", "id"))
        total = len(projects)
        completed = 0
        failed = 0

        for project in projects:
            _touch_job(job, f"{project.project_number} ECM 자동화 진행 중")
            _mark_project(project, DownloadReviewProjectStatus.RUNNING, "ECM 폴더 선택 중")

            # --- 5~6단계: ECM 웹페이지 자동화 ---
            ecm_result: DownloadStepResult = await run_ecm_automation(
                browser, project.project_number
            )

            if not ecm_result.success:
                _fail_project(
                    job, project, ecm_result.error_step, ecm_result.error_message,
                    event_code="ecm_download_failed",
                )
                failed += 1
                _update_job_counts(job, completed=completed, failed=failed, total=total)
                continue

            # --- 7~8단계: Windows 팝업 자동화 (동기) ---
            _mark_project(
                project, DownloadReviewProjectStatus.RUNNING,
                f"폴더 선택 및 다운로드 대기 중 (문서 {ecm_result.doc_count}건)",
            )

            popup_result: PopupResult = await asyncio.to_thread(
                handle_folder_popup_and_download,
                project.project_number,
                str(job.id),
            )

            if popup_result.success:
                # --- 9단계: 다운로드 파일 확인 ---
                _mark_project(
                    project, DownloadReviewProjectStatus.DOWNLOADED,
                    "다운로드 파일 확인 중",
                )
                verify_result = await asyncio.to_thread(
                    verify_downloaded_files,
                    popup_result.download_dir,
                    project.project_number,
                )
                file_summary = await asyncio.to_thread(
                    summarize_files, verify_result,
                )

                if verify_result.success:
                    project.status = DownloadReviewProjectStatus.COMPLETED
                    project.current_step = f"다운로드 완료 ({verify_result.file_count}개 파일)"
                    project.download_dir = popup_result.download_dir
                    project.completed_at = timezone.now()
                    project.save(
                        update_fields=[
                            "status", "current_step", "download_dir",
                            "completed_at", "updated_at",
                        ]
                    )
                    DownloadReviewLog.objects.create(
                        job=job,
                        job_project=project,
                        level=DownloadReviewLogLevel.INFO,
                        event_code="download_verified",
                        message=f"{project.project_number} 다운로드 확인 완료: {verify_result.file_count}개 파일",
                        detail_json=file_summary,
                    )
                    completed += 1
                else:
                    _fail_project(
                        job, project,
                        "다운로드 파일 확인",
                        verify_result.error_message,
                        event_code="download_verify_failed",
                    )
                    failed += 1
            else:
                _fail_project(
                    job, project, popup_result.error_step, popup_result.error_message,
                    event_code="agent_popup_failed",
                )
                failed += 1

            _update_job_counts(job, completed=completed, failed=failed, total=total)

        if failed == total:
            job.status = DownloadReviewJobStatus.FAILED
            job.last_error_message = "모든 프로젝트가 실패했습니다."
        else:
            job.status = DownloadReviewJobStatus.COMPLETED
        job.completed_at = timezone.now()
        job.progress_message = f"다운로드 완료: 성공 {completed}건, 실패 {failed}건"
        job.save(update_fields=[
            "status", "completed_at", "progress_message", "last_error_message", "updated_at",
        ])
    finally:
        await close_browser(browser)


def _fail_project(job, project, error_step, error_message, event_code="project_failed"):
    """프로젝트를 실패 처리하고 로그를 남긴다."""
    project.status = DownloadReviewProjectStatus.FAILED
    project.current_step = error_step
    project.error_message = error_message
    project.completed_at = timezone.now()
    project.save(
        update_fields=[
            "status", "current_step", "error_message",
            "completed_at", "updated_at",
        ]
    )
    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.WARNING,
        event_code=event_code,
        message=f"{project.project_number} 실패: {error_message}",
        detail_json={"step": error_step, "error": error_message},
    )


def claim_next_job(now=None):
    current = now or timezone.now()
    workflow_alias = getattr(settings, "WORKFLOW_DATABASE_ALIAS", "workflow")
    owner = _worker_owner()

    with transaction.atomic(using=workflow_alias):
        lock, _ = DownloadReviewLock.objects.select_for_update().get_or_create(id=1)
        if lock.locked:
            return None

        job = _next_startable_job(current)
        if job is None:
            return None

        lock.locked = True
        lock.owner = owner
        lock.job = job
        lock.locked_at = current
        lock.heartbeat_at = current
        lock.note = "download-review dry-run"
        lock.save(update_fields=["locked", "owner", "job", "locked_at", "heartbeat_at", "note", "updated_at"])

        job.status = DownloadReviewJobStatus.RUNNING
        job.started_at = job.started_at or current
        job.queued_at = job.queued_at or current
        job.worker_pid = os.getpid()
        job.worker_host = socket.gethostname()
        job.worker_heartbeat_at = current
        job.progress_message = "dry-run 작업 시작"
        job.save(
            update_fields=[
                "status",
                "started_at",
                "queued_at",
                "worker_pid",
                "worker_host",
                "worker_heartbeat_at",
                "progress_message",
                "updated_at",
            ]
        )
        DownloadReviewLog.objects.create(
            job=job,
            level=DownloadReviewLogLevel.INFO,
            event_code="dry_run_started",
            message="dry-run worker가 작업을 시작했습니다.",
        )
        return job


def run_dry_run_job(job, *, sleep_seconds=0):
    projects = list(job.projects.order_by("created_at", "id"))
    total = len(projects)
    completed = 0
    failed = 0

    for index, project in enumerate(projects):
        _touch_job(job, f"{project.project_number} dry-run 처리 중")
        _mark_project(project, DownloadReviewProjectStatus.RUNNING, "dry-run zip 다운로드 준비")
        _maybe_sleep(sleep_seconds)
        _mark_project(project, DownloadReviewProjectStatus.DOWNLOADED, "dry-run zip 다운로드 완료")
        _maybe_sleep(sleep_seconds)
        _mark_project(project, DownloadReviewProjectStatus.INSPECTING, "dry-run 점검규칙 검사 중")

        outcome = index % 3
        if outcome == 2:
            _finish_project_as_failed(project)
            failed += 1
        else:
            needs_fix = outcome == 1
            _write_dry_run_rule_results(project, needs_fix=needs_fix)
            _finish_project_as_completed(project, needs_fix=needs_fix)
            completed += 1

        _update_job_counts(job, completed=completed, failed=failed, total=total)

    job.status = DownloadReviewJobStatus.COMPLETED
    job.completed_at = timezone.now()
    job.progress_message = "dry-run 작업 완료"
    job.last_error_message = "일부 프로젝트가 보류되었습니다." if failed else ""
    job.save(update_fields=["status", "completed_at", "progress_message", "last_error_message", "updated_at"])
    DownloadReviewLog.objects.create(
        job=job,
        level=DownloadReviewLogLevel.INFO,
        event_code="dry_run_completed",
        message=f"dry-run 작업을 완료했습니다. 완료 {completed}건, 실패 {failed}건",
        detail_json={"completed": completed, "failed": failed},
    )


def mark_job_failed(job, message):
    job.status = DownloadReviewJobStatus.FAILED
    job.completed_at = timezone.now()
    job.progress_message = "worker 오류로 작업 실패"
    job.last_error_message = message
    job.save(update_fields=["status", "completed_at", "progress_message", "last_error_message", "updated_at"])
    DownloadReviewLog.objects.create(
        job=job,
        level=DownloadReviewLogLevel.ERROR,
        event_code="worker_failed",
        message="worker 처리 중 오류가 발생했습니다.",
        detail_json={"error": message},
        admin_only=True,
    )


def release_worker_lock(job):
    lock = DownloadReviewLock.objects.filter(id=1).first()
    if lock is None:
        return
    if lock.job_id and lock.job_id != job.id:
        return
    lock.locked = False
    lock.owner = ""
    lock.job = None
    lock.locked_at = None
    lock.heartbeat_at = None
    lock.note = ""
    lock.save(update_fields=["locked", "owner", "job", "locked_at", "heartbeat_at", "note", "updated_at"])


def _next_startable_job(now):
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
        .filter(status=DownloadReviewJobStatus.SCHEDULED, available_after__lte=now)
        .order_by("available_after", "requested_at", "id")
        .first()
    )


def _write_dry_run_rule_results(project, *, needs_fix):
    DownloadReviewRuleResult.objects.filter(job_project=project).delete()
    failing_rule_index = 10
    results = []
    for index, rule_name in enumerate(DRY_RUN_RULES, start=1):
        failed = needs_fix and index == failing_rule_index
        status = DownloadReviewRuleStatus.FAIL if failed else DownloadReviewRuleStatus.PASS
        results.append(
            DownloadReviewRuleResult(
                job_project=project,
                rule_code=f"dry-run-{index:02d}",
                rule_name=rule_name,
                sequence=index,
                file_path=f"{project.project_number}/dry-run/{rule_name}.txt",
                file_name=f"{rule_name}.txt",
                status=status,
                expected="기준값 충족",
                actual="회사명 불일치" if failed else "기준값 충족",
                message="부적합 샘플 결과입니다." if failed else "정상 확인",
                raw_detail_json={"dry_run": True},
            )
        )
    DownloadReviewRuleResult.objects.bulk_create(results)


def _finish_project_as_completed(project, *, needs_fix):
    completed_at = timezone.now()
    project.status = DownloadReviewProjectStatus.COMPLETED
    project.review_status = (
        DownloadReviewProjectReviewStatus.NEEDS_FIX
        if needs_fix
        else DownloadReviewProjectReviewStatus.COMPLETED
    )
    project.current_step = "dry-run 점검 완료"
    project.error_message = ""
    project.error_detail = ""
    project.zip_file_name = f"{project.project_number}_dry_run.zip"
    project.download_dir = f"C:/GSCert/downloads/{project.project_number}"
    project.completed_at = completed_at
    project.save(
        update_fields=[
            "status",
            "review_status",
            "current_step",
            "error_message",
            "error_detail",
            "zip_file_name",
            "download_dir",
            "completed_at",
            "updated_at",
        ]
    )
    write_project_review_result(
        project.project_number,
        "수정 필요" if needs_fix else "완료",
        artifact_results=_dry_run_artifact_results(needs_fix=needs_fix),
        inspected_at=completed_at,
    )


def _finish_project_as_failed(project):
    completed_at = timezone.now()
    project.status = DownloadReviewProjectStatus.FAILED
    project.review_status = DownloadReviewProjectReviewStatus.HELD
    project.current_step = "dry-run 전송현황 대기"
    project.error_message = "dry-run 샘플 실패"
    project.error_detail = (
        "전송현황 창은 종료되었지만 프로젝트 zip 파일이 확인되지 않은 상황을 가정한 샘플 오류입니다."
    )
    project.zip_file_name = ""
    project.completed_at = completed_at
    project.save(
        update_fields=[
            "status",
            "review_status",
            "current_step",
            "error_message",
            "error_detail",
            "zip_file_name",
            "completed_at",
            "updated_at",
        ]
    )
    write_project_review_result(
        project.project_number,
        "보류",
        artifact_results=_dry_run_artifact_results(held=True),
        inspected_at=completed_at,
    )
    DownloadReviewLog.objects.create(
        job=project.job,
        job_project=project,
        level=DownloadReviewLogLevel.WARNING,
        event_code="dry_run_project_failed",
        message=f"{project.project_number} dry-run 샘플 실패",
        detail_json={"dry_run": True, "step": project.current_step},
    )


def _mark_project(project, status, step):
    project.status = status
    project.current_step = step
    project.started_at = project.started_at or timezone.now()
    project.save(update_fields=["status", "current_step", "started_at", "updated_at"])


def _update_job_counts(job, *, completed, failed, total):
    job.completed_project_count = completed
    job.failed_project_count = failed
    job.requested_project_count = total
    job.worker_heartbeat_at = timezone.now()
    job.progress_message = f"dry-run 진행 중: 완료 {completed}건, 실패 {failed}건"
    job.save(
        update_fields=[
            "completed_project_count",
            "failed_project_count",
            "requested_project_count",
            "worker_heartbeat_at",
            "progress_message",
            "updated_at",
        ]
    )


def _touch_job(job, message):
    job.worker_heartbeat_at = timezone.now()
    job.progress_message = message
    job.save(update_fields=["worker_heartbeat_at", "progress_message", "updated_at"])


def _maybe_sleep(seconds):
    if seconds:
        time.sleep(seconds)


def _dry_run_artifact_results(*, needs_fix=False, held=False):
    if held:
        return {column: "X" for column in ARTIFACT_REVIEW_COLUMNS}

    results = {column: "정상" for column in ARTIFACT_REVIEW_COLUMNS}
    if needs_fix:
        results["시험성적서(PDF)"] = "부적합"
    return results


def _worker_owner():
    return f"{socket.gethostname()}:{os.getpid()}"
