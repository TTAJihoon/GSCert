"""KOLAS '결과서 다운로드' 진행률 기록·조회.

다운로드는 zip 이 브라우저로 스트리밍되는 요청 하나라서, 서버가 그 요청을 처리하는 동안 프로젝트 단위로
KolasReportTask(workflow DB)를 갱신하고, 화면은 /kolas/api/report-tasks/ 를 폴링해 progress bar 로 보여준다.

진행률은 '얼추'다: (끝낸 프로젝트 수 + 현재 프로젝트의 단계 비율) / 전체 프로젝트 수. 완료 전에는 99% 를 넘기지 않고
정상 종료 때 100% 로 확정한다. 진행률 기록 실패가 다운로드를 깨뜨리지 않도록 모든 DB 쓰기는 예외를 삼킨다.
"""

import logging
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from main.models import KolasReportTask, KolasReportTaskStatus

logger = logging.getLogger(__name__)

STALE_AFTER_SECONDS = 180
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
STATUS_LABELS = {
    KolasReportTaskStatus.RUNNING: "진행 중",
    KolasReportTaskStatus.COMPLETED: "완료",
    KolasReportTaskStatus.FAILED: "실패",
    KolasReportTaskStatus.CANCELED: "취소됨",
}

# 프로젝트 1건 안에서의 단계별 비율(0~1). 서버 저장본은 빠르고, ECM 은 폴더/zip 탐색과 다운로드가 대부분이다.
STEP_CHECK_STORAGE = 0.05
STEP_LOCATING = 0.10
STEP_LOCATED = 0.40
STEP_ANON_LOOKUP = 0.55
STEP_FILES_END = 0.95


def _alias():
    return getattr(settings, "WORKFLOW_DATABASE_ALIAS", "workflow")


def parse_task_id(value):
    """클라이언트가 보낸 task_id(UUID)를 검증한다. 형식이 틀리거나 비어 있으면 새로 만든다."""
    try:
        return uuid.UUID(str(value or "").strip())
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid4()


class ReportTaskReporter:
    """iter_report_zip 이 호출하는 진행률 기록기. 모든 메서드는 예외를 던지지 않는다."""

    def __init__(self, task_id, total, *, min_interval=0.4, clock=time.monotonic):
        self.task_id = task_id
        self.total = max(int(total), 0)
        self._min_interval = min_interval
        self._clock = clock
        self._last_write = 0.0
        self._last_state = None
        self.finished = False
        self._index = 0

    # ----- 생성 -----
    @classmethod
    def start(cls, task_id, total, requested_ip=None, **kwargs):
        reporter = cls(task_id, total, **kwargs)
        try:
            KolasReportTask.objects.using(_alias()).update_or_create(
                id=task_id,
                defaults={
                    "status": KolasReportTaskStatus.RUNNING,
                    "requested_ip": requested_ip or None,
                    "total_projects": reporter.total,
                    "done_projects": 0,
                    "percent": 0,
                    "current_project": "",
                    "current_step": "시작 준비 중",
                    "finished_at": None,
                    "error_message": "",
                },
            )
        except Exception:
            logger.warning("KOLAS report task create failed", exc_info=True)
        return reporter

    # ----- 진행 -----
    def percent_for(self, index, fraction):
        if self.total <= 0:
            return 0
        value = (index + max(0.0, min(1.0, fraction))) / self.total * 100
        return min(99, int(value))

    def step(self, index, number, text, fraction):
        """index(0부터) 번째 프로젝트의 진행 단계를 기록한다. 같은 상태 반복·너무 잦은 기록은 건너뛴다."""
        self._index = index
        percent = self.percent_for(index, fraction)
        state = (number, text, percent)
        now = self._clock()
        if state == self._last_state:
            return
        if now - self._last_write < self._min_interval and number == (self._last_state or ("",))[0]:
            return
        self._last_state = state
        self._last_write = now
        self._update(
            percent=percent, done_projects=min(index, self.total), current_project=number or "", current_step=text,
        )

    def project_done(self, index, number, text="완료"):
        self._index = index + 1
        percent = self.percent_for(index + 1, 0)
        self._last_state = (number, text, percent)
        self._last_write = self._clock()
        self._update(percent=percent, done_projects=min(index + 1, self.total), current_project=number or "", current_step=text)

    # ----- 종료 -----
    def finish(self, rows):
        """모든 프로젝트 처리를 마치고 zip 의 마지막 조각을 보내기 직전에 호출한다."""
        known = [row for row in rows if not getattr(row, "unknown", False)]
        self.finished = True
        self._update(
            status=KolasReportTaskStatus.COMPLETED,
            percent=100,
            done_projects=self.total,
            current_project="",
            current_step="완료",
            complete_count=sum(1 for row in known if row.has_word and row.has_pdf),
            partial_count=sum(1 for row in known if row.has_word != row.has_pdf),
            none_count=sum(1 for row in known if not row.has_word and not row.has_pdf),
            anonymous_count=sum(1 for row in known if row.anonymous),
            finished_at=timezone.now(),
        )

    def cancel(self):
        if self.finished:
            return
        self.finished = True
        self._update(
            status=KolasReportTaskStatus.CANCELED, current_step="다운로드가 중단되었습니다.", finished_at=timezone.now(),
        )

    def fail(self, exc):
        if self.finished:
            return
        self.finished = True
        self._update(
            status=KolasReportTaskStatus.FAILED, current_step="오류로 중단되었습니다.",
            error_message=str(exc)[:1000], finished_at=timezone.now(),
        )

    # ----- 내부 -----
    def _update(self, **fields):
        try:
            fields["updated_at"] = timezone.now()
            KolasReportTask.objects.using(_alias()).filter(pk=self.task_id).update(**fields)
        except Exception:
            logger.warning("KOLAS report task update failed", exc_info=True)


def tracked_stream(chunks, reporter):
    """응답 본문 생성기를 감싸 브라우저가 중간에 끊거나(GeneratorExit) 예외가 나면 작업 상태를 마무리한다."""
    try:
        yield from chunks
    except GeneratorExit:
        reporter.cancel()
        raise
    except Exception as exc:
        reporter.fail(exc)
        raise
    else:
        if not reporter.finished:  # 요약 전에 끝난 비정상 경로 방어
            reporter.fail("진행 기록 없이 종료")


def mark_stale_tasks():
    """서버 재시작 등으로 갱신이 끊긴 진행 중 작업을 실패로 정리한다."""
    try:
        cutoff = timezone.now() - timedelta(seconds=STALE_AFTER_SECONDS)
        KolasReportTask.objects.using(_alias()).filter(
            status=KolasReportTaskStatus.RUNNING, updated_at__lt=cutoff,
        ).update(
            status=KolasReportTaskStatus.FAILED,
            current_step="갱신이 끊겨 중단된 것으로 처리했습니다(서버 재시작 등).",
            finished_at=timezone.now(),
        )
    except Exception:
        logger.warning("KOLAS report stale cleanup failed", exc_info=True)


def serialize_task(task):
    def iso(value):
        return timezone.localtime(value).isoformat() if value else None

    return {
        "id": str(task.id),
        "status": task.status,
        "status_label": STATUS_LABELS.get(task.status, task.status),
        "percent": int(task.percent),
        "total_projects": task.total_projects,
        "done_projects": task.done_projects,
        "current_project": task.current_project,
        "current_step": task.current_step,
        "complete_count": task.complete_count,
        "partial_count": task.partial_count,
        "none_count": task.none_count,
        "anonymous_count": task.anonymous_count,
        "error_message": task.error_message,
        "started_at": iso(task.started_at),
        "finished_at": iso(task.finished_at),
    }


def list_tasks(limit=DEFAULT_LIMIT):
    mark_stale_tasks()
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    try:
        tasks = list(KolasReportTask.objects.using(_alias()).order_by("-started_at", "id")[:limit])
    except Exception:
        # 새 코드를 올렸지만 `migrate --database=workflow`(0016) 전이면 테이블이 없다. 화면은 빈 목록으로 둔다.
        logger.warning("KOLAS report task list failed (migrate --database=workflow 필요?)", exc_info=True)
        return []
    return [serialize_task(task) for task in tasks]
