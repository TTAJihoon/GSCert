import asyncio
import os
import shutil
import socket
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
import logging

from asgiref.sync import sync_to_async
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
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS, write_project_review_result
from main.views.review.ecm_download_review_inspection import (
    DownloadReviewCleanupSafetyError,
    DownloadReviewInspectionError,
    _validate_cleanup_target,
    cleanup_download_dir,
    cleanup_stale_project_history,
    run_download_inspection,
)
from main.views.review.ecm_download_review_centers import worker_allowed_centers
from main.views.review.artifact_source import JobCanceledError, build_artifact_source


logger = logging.getLogger("main.views.review.ecm_download_review_worker")


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


async def _run_sync(func, *args, **kwargs):
    return await sync_to_async(func, thread_sensitive=True)(*args, **kwargs)


@dataclass(frozen=True)
class WorkerRunResult:
    processed: bool
    job_id: str | None = None
    status: str = "idle"
    message: str = ""


def run_worker_once(*, dry_run=False, sleep_seconds=0, headless=True, source_name=None):
    if not dry_run:
        return _run_live_worker(headless=headless, source_name=source_name)

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



def _run_on_proactor(coro):
    """coro 를 ProactorEventLoop 에서 실행한다.

    Windows 에서 Playwright 가 브라우저 서브프로세스를 띄우려면 ProactorEventLoop
    가 필요하다. INSTALLED_APPS 에 'daphne' 가 추가되면서 전역 이벤트 루프 정책이
    WindowsSelectorEventLoopPolicy 로 바뀌어, worker 의 asyncio.run() 이 Selector
    루프를 만들고 create_subprocess_exec 가 NotImplementedError 로 실패했다.
    전역 정책과 무관하게 명시적으로 Proactor 루프를 만들어 실행한다.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


def _run_live_worker(*, headless=True, source_name=None):
    """실제 자동화(기본 ECM, source_name 으로 변경 가능)를 사용하는 worker 실행."""
    claim = claim_next_job()
    if claim is None:
        return WorkerRunResult(
            processed=False,
            status="idle",
            message="시작 가능한 작업이 없습니다.",
        )

    job = claim
    try:
        _run_on_proactor(_run_live_job(job, headless=headless, source_name=source_name))
        job.refresh_from_db()
        return WorkerRunResult(
            processed=True,
            job_id=str(job.id),
            status=job.status,
            message=job.progress_message or "ECM 다운로드 자동화 작업을 완료했습니다.",
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


def _job_canceled(job):
    """작업이 외부(강제 종료/취소)에서 CANCELED 로 바뀌었는지 DB 에서 확인한다.

    force_stop_download_review_jobs 는 DB 상태만 CANCELED 로 바꾸고 실행 중인 워커
    프로세스는 건드리지 않으므로, 워커가 주기적으로 이 신호를 확인해 스스로 멈춰야
    '강제 종료'가 실제로 동작한다.
    """
    try:
        job.refresh_from_db(fields=["status"])
    except Exception:
        return False
    return job.status == DownloadReviewJobStatus.CANCELED


async def _run_live_job(job, *, headless=True, source_name=None):
    """작업 단위로 browser를 launch/close하고 프로젝트를 순차 처리한다.

    각 프로젝트에 대해:
    1. ECM 웹페이지1에서 프로젝트 폴더 선택 → 전체 선택 → 다운로드 메뉴 클릭 (5~6단계)
    2. Windows 폴더 찾아보기 팝업에서 다운로드 폴더 선택 (7단계)
    3. 전송현황 창 대기 및 시스템 알림 처리 (8단계)
    """
    from main.views.review.ecm_download_verify import summarize_files, verify_downloaded_files

    # 산출물 source 선택: 인자 > settings.DOWNLOAD_REVIEW_SOURCE > "ecm-http".
    # 추후 로컬/다른 저장소로 갈아끼우려면 이 source 만 교체한다(워커 흐름은 불변).
    source_name = source_name or getattr(settings, "DOWNLOAD_REVIEW_SOURCE", "ecm-http")
    source = build_artifact_source(
        source_name,
        headless=headless,
        source_root=getattr(settings, "LOCAL_ARTIFACT_SOURCE_ROOT", None),
    )
    await source.open()
    try:
        projects = await _run_sync(_projects_for_job, job)
        total = len(projects)
        completed = 0
        failed = 0

        for project in projects:
            # 강제 종료(취소) 시 남은 프로젝트를 더 처리하지 않고 즉시 중단한다.
            if await _run_sync(_job_canceled, job):
                logger.info("강제 종료 감지 → 남은 프로젝트 처리를 중단합니다: job=%s", job.id)
                break
            await _run_sync(_touch_job, job, f"{project.project_number} ECM 자동화 진행 중")
            await _run_sync(_mark_project, project, DownloadReviewProjectStatus.RUNNING, "ECM 폴더 선택 중")

            async def _on_progress(relative_path, doc_count):
                path_text = " > ".join([project.project_number, *relative_path])
                await _run_sync(
                    _mark_project,
                    project, DownloadReviewProjectStatus.RUNNING,
                    f"다운로드 중: {path_text} (문서 {doc_count}건)",
                )

            async def _is_canceled():
                return await _run_sync(_job_canceled, job)

            # 다운로드 시작 전, 남아 있는 이전 산출물을 비운다(모든 source 공통: 같은
            # 폴더로 다시 받을 때 '덮어쓰기 확인' 팝업/혼입 방지). source 동시성 제어
            # (ECM 에이전트 락 등)는 각 source.fetch 내부 책임이다.
            await _run_sync(_clear_project_download_dir, job, project)

            try:
                ecm_result = await source.fetch(
                    project,
                    on_progress=_on_progress,
                    is_canceled=_is_canceled,
                )
            except JobCanceledError:
                logger.info("강제 종료 감지(다운로드 중) → 처리를 중단합니다: job=%s", job.id)
                break

            if ecm_result.success:
                # --- 9단계: 다운로드 파일 확인 ---
                await _run_sync(
                    _mark_project,
                    project, DownloadReviewProjectStatus.DOWNLOADED,
                    f"다운로드 파일 확인 중 ({ecm_result.downloaded_folder_count}개 폴더)",
                )
                # 전송 직후 파일이 아직 디스크에 기록 중일 수 있으므로
                # 0개이면 최대 3회(3초 간격) 재시도한다.
                verify_result = None
                for _verify_attempt in range(4):
                    verify_result = await asyncio.to_thread(
                        verify_downloaded_files,
                        ecm_result.download_dir,
                        project.project_number,
                    )
                    if verify_result.success or _verify_attempt >= 3:
                        break
                    logger.warning(
                        "%s 파일 0개 감지 (시도 %d/3). 3초 후 재확인...",
                        project.project_number, _verify_attempt + 1,
                    )
                    await asyncio.sleep(3)
                file_summary = await asyncio.to_thread(
                    summarize_files, verify_result,
                )

                if verify_result.success:
                    await _run_sync(
                        _record_download_verified,
                        job,
                        project,
                        ecm_result.download_dir,
                        verify_result.file_count,
                        file_summary,
                    )
                    await _run_sync(
                        _mark_project,
                        project, DownloadReviewProjectStatus.RUNNING,
                        "산출물 보관 중 (ecm 폴더로 복사)",
                    )
                    await _run_sync(
                        _archive_download_dir_safely,
                        job, project, ecm_result.download_dir,
                    )
                    await _run_sync(
                        _mark_project,
                        project,
                        DownloadReviewProjectStatus.INSPECTING,
                        "점검규칙 검사 중",
                    )
                    try:
                        inspection_outcome = await _run_sync(
                            run_download_inspection,
                            project,
                            verify_result,
                            file_summary,
                        )
                    except DownloadReviewInspectionError as exc:
                        await _run_sync(
                            _fail_project,
                            job, project, "점검규칙 검사", str(exc),
                            event_code="inspection_failed",
                            detail_json=file_summary,
                            download_dir=ecm_result.download_dir,
                        )
                        failed += 1
                    else:
                        await _run_sync(
                            _finish_project_after_inspection,
                            job,
                            project,
                            inspection_outcome,
                            verify_result.file_count,
                            file_summary,
                        )
                        completed += 1
                    finally:
                        await _run_sync(_cleanup_download_dir_safely, job, project)
                else:
                    await _run_sync(
                        _fail_project,
                        job, project,
                        "다운로드 파일 확인",
                        verify_result.error_message,
                        event_code="download_verify_failed",
                        detail_json=file_summary,
                        download_dir=ecm_result.download_dir,
                    )
                    await _run_sync(_cleanup_download_dir_safely, job, project)
                    failed += 1
            else:
                await _run_sync(
                    _fail_project,
                    job, project, ecm_result.error_step, ecm_result.error_message,
                    event_code="ecm_download_failed",
                    download_dir=ecm_result.download_dir,
                )
                if ecm_result.download_dir:
                    await _run_sync(_cleanup_download_dir_safely, job, project)
                failed += 1

            await _run_sync(_update_job_counts, job, completed=completed, failed=failed, total=total)

        # 강제 종료된 경우 완료(COMPLETED/FAILED)로 덮어쓰지 않는다(CANCELED 유지).
        if await _run_sync(_job_canceled, job):
            logger.info("작업이 강제 종료되어 완료 처리를 생략합니다: job=%s", job.id)
        else:
            await _run_sync(_finish_live_job, job, completed=completed, failed=failed, total=total)
    finally:
        await source.close()


def _fail_project(
    job,
    project,
    error_step,
    error_message,
    event_code="project_failed",
    *,
    detail_json=None,
    download_dir="",
):
    """프로젝트를 실패 처리하고 로그를 남긴다."""
    completed_at = timezone.now()
    project.status = DownloadReviewProjectStatus.FAILED
    project.review_status = DownloadReviewProjectReviewStatus.HELD
    project.current_step = error_step
    project.error_message = error_message
    if detail_json:
        project.error_detail = _user_error_detail(detail_json)
    if download_dir:
        project.download_dir = download_dir
    project.completed_at = completed_at
    update_fields = [
        "status", "review_status", "current_step", "error_message",
        "completed_at", "updated_at",
    ]
    if detail_json:
        update_fields.append("error_detail")
    if download_dir:
        update_fields.append("download_dir")
    project.save(
        update_fields=update_fields
    )
    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.WARNING,
        event_code=event_code,
        message=f"{project.project_number} 실패: {error_message}",
        detail_json={"step": error_step, "error": error_message, **(detail_json or {})},
    )
    _write_reference_result_safely(project, "실패", inspected_at=completed_at)


def _user_error_detail(detail_json):
    if not detail_json:
        return ""
    file_names = detail_json.get("file_names") or []
    warnings = detail_json.get("warnings") or []
    parts = []
    if file_names:
        parts.append("확인된 파일: " + ", ".join(str(name) for name in file_names[:10]))
    if warnings:
        parts.append("경고: " + " / ".join(str(message) for message in warnings[:5]))
    if detail_json.get("file_count") is not None:
        parts.append(f"파일 수: {detail_json.get('file_count')}")
    return "\n".join(parts)


def _record_download_verified(job, project, download_dir, file_count, file_summary):
    completed_at = timezone.now()
    project.status = DownloadReviewProjectStatus.DOWNLOADED
    project.review_status = DownloadReviewProjectReviewStatus.UNREVIEWED
    project.current_step = f"다운로드 완료 ({file_count}개 파일)"
    project.download_dir = download_dir
    project.completed_at = completed_at
    project.save(
        update_fields=[
            "status", "review_status", "current_step", "download_dir",
            "completed_at", "updated_at",
        ]
    )
    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.INFO,
        event_code="download_verified",
        message=f"{project.project_number} 다운로드 확인 완료: {file_count}개 파일",
        detail_json=file_summary,
    )


def _finish_project_after_inspection(job, project, outcome, file_count, file_summary):
    completed_at = timezone.now()
    project.status = DownloadReviewProjectStatus.COMPLETED
    project.review_status = outcome.project_review_status
    project.current_step = (
        f"점검 완료: 정상 {outcome.passed_count}건, "
        f"부적합 {outcome.failed_count}건"
    )
    project.error_message = ""
    project.error_detail = ""
    project.completed_at = completed_at
    project.save(
        update_fields=[
            "status",
            "review_status",
            "current_step",
            "error_message",
            "error_detail",
            "completed_at",
            "updated_at",
        ]
    )
    _write_reference_result_safely(
        project,
        outcome.reference_review,
        artifact_results=outcome.artifact_results,
        inspected_at=completed_at,
    )
    # 새 결과가 정상 저장된 뒤이므로, 같은 프로젝트의 이전 점검 이력(산출물 폴더 +
    # DB 행)은 이제 필요 없다 — 지워서 재점검할수록 디스크/DB가 쌓이는 걸 막는다.
    cleanup_summary = cleanup_stale_project_history(project)
    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.INFO,
        event_code="inspection_completed",
        message=(
            f"{project.project_number} 점검 완료: "
            f"정상 {outcome.passed_count}건, 부적합 {outcome.failed_count}건"
        ),
        detail_json={
            "file_count": file_count,
            "rule_result_count": outcome.result_count,
            "reference_review": outcome.reference_review,
            "artifact_results": outcome.artifact_results,
            "files": file_summary,
            "old_history_cleanup": cleanup_summary,
        },
    )


def _clear_project_download_dir(job, project):
    """프로젝트 다운로드를 *시작하기 전에* 대상 폴더(base/<프로젝트번호>)를 무조건 비운다.

    이전 요청이 점검 도중 실패하면 다운로드 폴더가 정리되지 않고 남는데, 다음 요청에서
    같은 폴더로 다시 받으면 ECM 에이전트가 '덮어쓰기 확인' 팝업을 띄워 작업이 멈춘다.
    시작 시 깨끗이 비워 항상 새로 받도록 한다.

    프로젝트 DB 상태(zip_deleted_at 등)는 건드리지 않는다 — 순수 디스크 정리.
    경로 안전 검증 후 폴더가 있을 때만 삭제하며, 실패해도 작업을 중단시키지 않는다.
    """
    base_dir = Path(getattr(settings, "AGENT_DOWNLOAD_BASE_DIR")).resolve()
    # 팝업 핸들러(ecm_agent_popup)가 만드는 폴더명과 동일하게 NFC 정규화한다.
    project_number = unicodedata.normalize("NFC", project.project_number)
    target = (base_dir / project_number).resolve()

    try:
        _validate_cleanup_target(project.project_number, base_dir, target)
    except DownloadReviewCleanupSafetyError as exc:
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="download_preclean_skipped",
            message=f"{project.project_number} 다운로드 폴더 사전 정리 생략: {exc}",
            detail_json={"target": str(target), "error": str(exc)},
            admin_only=True,
        )
        return

    if not target.exists():
        return

    try:
        file_count = sum(1 for item in target.rglob("*") if item.is_file())
        shutil.rmtree(target)
    except Exception as exc:
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="download_preclean_failed",
            message=f"{project.project_number} 다운로드 폴더 사전 정리 실패: {exc}",
            detail_json={"target": str(target), "error": str(exc)},
            admin_only=True,
        )
        return

    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.INFO,
        event_code="download_preclean",
        message=f"{project.project_number} 다운로드 폴더 사전 정리: 기존 {file_count}개 파일 삭제",
        detail_json={"target": str(target), "file_count": file_count},
        admin_only=True,
    )


def _cleanup_download_dir_safely(job, project):
    try:
        outcome = cleanup_download_dir(project)
    except DownloadReviewCleanupSafetyError as exc:
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="download_cleanup_skipped",
            message=f"{project.project_number} 다운로드 폴더 삭제 생략: {exc}",
            detail_json={"download_dir": project.download_dir, "error": str(exc)},
            admin_only=True,
        )
        return
    except Exception as exc:
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="download_cleanup_failed",
            message=f"{project.project_number} 다운로드 폴더 삭제 실패: {exc}",
            detail_json={"download_dir": project.download_dir, "error": str(exc)},
            admin_only=True,
        )
        return

    DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        level=DownloadReviewLogLevel.INFO,
        event_code="download_cleanup_completed" if outcome.deleted else "download_cleanup_skipped",
        message=f"{project.project_number} {outcome.message}",
        detail_json={
            "download_dir": project.download_dir,
            "deleted": outcome.deleted,
            "file_count": outcome.file_count,
        },
    )


def _archive_download_dir_safely(job, project, download_dir):
    """다운로드 폴더를 ecm 보관 경로로 복사한다. 실패해도 점검을 중단하지 않는다."""
    archive_base = getattr(settings, "AGENT_ARCHIVE_BASE_DIR", "")
    if not archive_base:
        return

    src = Path(download_dir)
    dst = Path(archive_base) / project.project_number
    try:
        shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.INFO,
            event_code="archive_completed",
            message=f"{project.project_number} 산출물 보관 완료: {dst}",
            detail_json={"download_dir": str(src), "archive_dir": str(dst)},
        )
    except Exception as exc:
        DownloadReviewLog.objects.create(
            job=job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="archive_failed",
            message=f"{project.project_number} 산출물 보관 실패 (점검은 계속 진행): {exc}",
            detail_json={"download_dir": str(src), "archive_dir": str(dst), "error": str(exc)},
        )


def _finish_live_job(job, *, completed, failed, total):
    if failed == total:
        job.status = DownloadReviewJobStatus.FAILED
        job.last_error_message = "모든 프로젝트가 실패했습니다."
    else:
        job.status = DownloadReviewJobStatus.COMPLETED
        job.last_error_message = ""
    job.completed_at = timezone.now()
    job.progress_message = f"다운로드 완료: 성공 {completed}건, 실패 {failed}건"
    job.save(update_fields=[
        "status", "completed_at", "progress_message", "last_error_message", "updated_at",
    ])


async def _close_ecm_page(page):
    if page is None:
        return
    try:
        context = page.context
        await page.close()
        await context.close()
    except Exception:
        logger.debug("ECM page/context close failed", exc_info=True)


def _write_reference_result_safely(project, review, *, inspected_at, artifact_results=None):
    try:
        write_project_review_result(
            project.project_number,
            review,
            artifact_results=artifact_results,
            inspected_at=inspected_at,
            center_code=project.center_code,
        )
    except Exception as exc:
        logger.warning(
            "ecmlist write-back failed for %s: %s",
            project.project_number,
            exc,
            exc_info=True,
        )
        DownloadReviewLog.objects.create(
            job=project.job,
            job_project=project,
            level=DownloadReviewLogLevel.WARNING,
            event_code="reference_writeback_failed",
            message=f"{project.project_number} 기준 DB 갱신 실패: {exc}",
            detail_json={"review": review, "error": str(exc)},
            admin_only=True,
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
        lock.note = "download-review worker"
        lock.save(update_fields=["locked", "owner", "job", "locked_at", "heartbeat_at", "note", "updated_at"])

        job.status = DownloadReviewJobStatus.RUNNING
        job.started_at = job.started_at or current
        job.queued_at = job.queued_at or current
        job.worker_pid = os.getpid()
        job.worker_host = socket.gethostname()
        job.worker_heartbeat_at = current
        job.progress_message = "worker 작업 시작"
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
            event_code="worker_started",
            message="download-review worker가 작업을 시작했습니다.",
        )
        return job


def run_dry_run_job(job, *, sleep_seconds=0):
    projects = _projects_for_job(job)
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
    completed_at = timezone.now()
    job.status = DownloadReviewJobStatus.FAILED
    job.completed_at = completed_at
    job.progress_message = "worker 오류로 작업 실패"
    job.last_error_message = message
    job.save(update_fields=["status", "completed_at", "progress_message", "last_error_message", "updated_at"])
    job.projects.filter(
        status__in=(
            DownloadReviewProjectStatus.QUEUED,
            DownloadReviewProjectStatus.RUNNING,
            DownloadReviewProjectStatus.DOWNLOADED,
            DownloadReviewProjectStatus.INSPECTING,
        )
    ).update(
        status=DownloadReviewProjectStatus.FAILED,
        review_status=DownloadReviewProjectReviewStatus.HELD,
        current_step="worker 오류",
        error_message=message,
        completed_at=completed_at,
        updated_at=completed_at,
    )
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
    allowed_centers = worker_allowed_centers()
    queued = (
        DownloadReviewJob.objects
        .filter(status=DownloadReviewJobStatus.QUEUED)
        .filter(center_code__in=allowed_centers)
        .order_by("queued_at", "requested_at", "id")
        .first()
    )
    if queued:
        return queued

    return (
        DownloadReviewJob.objects
        .filter(status=DownloadReviewJobStatus.SCHEDULED, available_after__lte=now)
        .filter(center_code__in=allowed_centers)
        .order_by("available_after", "requested_at", "id")
        .first()
    )


def _projects_for_job(job):
    projects = list(job.projects.order_by("created_at", "id"))
    requested_order = {
        project_number: index
        for index, project_number in enumerate(job.selected_projects_json or [])
    }
    if not requested_order:
        return projects
    return sorted(
        projects,
        key=lambda project: (
            requested_order.get(project.project_number, len(requested_order)),
            project.created_at,
            str(project.id),
        ),
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
        "X" if needs_fix else "O",
        artifact_results=_dry_run_artifact_results(needs_fix=needs_fix),
        inspected_at=completed_at,
        center_code=project.center_code,
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
    job.progress_message = f"작업 진행 중: 완료 {completed}건, 실패 {failed}건"
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


def _dry_run_artifact_results(*, needs_fix=False):
    results = {column: "O" for column in ARTIFACT_REVIEW_COLUMNS}
    if needs_fix:
        results["시험성적서(PDF)"] = "X"
    return results


def _worker_owner():
    return f"{socket.gethostname()}:{os.getpid()}"
