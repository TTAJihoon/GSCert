import json
import re
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
import django_rq
from ...models import Job
from .history_tasks import run_playwright_job_task_sync  # 동기 래퍼

def _extract_fields(payload: dict):
    """
    payload에서 '시험번호'와 '인증일자'를 추출하고,
    인증일자로부터 연도(YYYY), 날짜(YYYYMMDD)를 계산해 반환.
    """
    test_no = payload.get("시험번호") or payload.get("test_no") or payload.get("cert_no")
    cert_date_raw = payload.get("인증일자") or payload.get("cert_date") or payload.get("인증일")

    if not test_no:
        raise ValueError("시험번호가 필요합니다.")

    if not cert_date_raw:
        raise ValueError("인증일자(예: 2025.08.25)가 필요합니다.")

    # 2025.08.25 / 2025-08-25 / 20250825 등 모두 허용
    digits = re.sub(r"\D", "", cert_date_raw)
    if len(digits) < 8:
        raise ValueError(f"인증일자 형식을 해석할 수 없습니다: {cert_date_raw!r}")

    date8 = digits[:8]       # YYYYMMDD
    year4 = date8[:4]        # YYYY

    return test_no, year4, date8, cert_date_raw

@csrf_exempt
def start_job(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # 원본 payload 파싱
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = request.POST.dict()

    # 필수값 추출 & 파생값 계산
    try:
        test_no, year4, date8, cert_date_raw = _extract_fields(payload)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    # 태스크로 넘길 data 구성 (원본 + 표준화 키 추가)
    data = dict(payload)  # 원본을 보존하면서
    data["시험번호"] = test_no         # 표준 키로 통일
    data["인증일자"] = cert_date_raw   # 원문도 같이 전달
    data["연도"] = year4               # 예: "2025"
    data["날짜"] = date8               # 예: "20250825"

    # 잡 생성 & 큐 등록
    job = Job.objects.create(status="PENDING")
    queue = django_rq.get_queue("default")
    queue.enqueue(run_playwright_job_task_sync, str(job.id), data)

    return JsonResponse({"jobId": str(job.id), "status": job.status})

def job_status(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    return JsonResponse({
        "jobId": str(job.id),
        "status": job.status,
        "final_link": job.final_link,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    })
