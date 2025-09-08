import json
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
import django_rq
from ...models import Job
from .history_tasks import run_playwright_job_task

@csrf_exempt
def start_job(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = request.POST.dict()

    # 필수값 체크
    test_no = data.get("시험번호") or data.get("test_no")
    if not test_no:
        return JsonResponse({"ok": False, "error": "시험번호가 필요합니다."}, status=400)

    job = Job.objects.create(status="PENDING")
    queue = django_rq.get_queue("default")
    # data(dict)를 그대로 전달 → 태스크에서 시나리오 입력으로 사용
    queue.enqueue(run_playwright_job_task, str(job.id), data)

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
