import json
import os
import subprocess
import threading
import uuid
from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from main.utils.llm_models import list_llm_models, select_llm_model

_VENV_PYTHON = r"C:\Claude_GSCert\.venv\Scripts\python.exe"
_CLAUDE_ROOT = r"C:\Claude_GSCert"

_tasks: dict = {}
_tasks_lock = threading.Lock()


def _new_task(label: str) -> tuple[str, dict]:
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "label": label,
        "status": "running",
        "lines": [],
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
    }
    with _tasks_lock:
        _tasks[task_id] = task
    return task_id, task


def _tail_process(proc: subprocess.Popen, task: dict):
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            with _tasks_lock:
                task["lines"].append(line)
        proc.wait()
        with _tasks_lock:
            task["status"] = "done" if proc.returncode == 0 else "error"
            task["finished_at"] = datetime.now().isoformat()
    except Exception as exc:
        with _tasks_lock:
            task["lines"].append(f"[오류] {exc}")
            task["status"] = "error"
            task["finished_at"] = datetime.now().isoformat()


def _launch(args: list, cwd: str, env: dict, task: dict):
    def _run():
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=env,
            )
            _tail_process(proc, task)
        except Exception as exc:
            with _tasks_lock:
                task["lines"].append(f"[실행 실패] {exc}")
                task["status"] = "error"
                task["finished_at"] = datetime.now().isoformat()

    threading.Thread(target=_run, daemon=True).start()


def server_console(request):
    return render(request, "server_console.html")


@require_GET
def api_llm_models(request):
    models = list_llm_models()
    active = next((model for model in models if model["active"]), None)
    return JsonResponse({"models": models, "active_model": active})


@csrf_exempt
@require_POST
def api_select_llm_model(request):
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "요청 JSON을 해석할 수 없습니다."}, status=400)

    models = list_llm_models()
    key = str(body.get("key") or "").strip()
    if not key:
        try:
            index = int(body.get("index"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "선택할 모델 번호를 입력해주세요."}, status=400)
        if index < 1 or index > len(models):
            return JsonResponse({"error": "목록에 있는 모델 번호를 입력해주세요."}, status=400)
        key = models[index - 1]["key"]

    try:
        selected = select_llm_model(key)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"selected_model": selected, "models": list_llm_models()})


@csrf_exempt
@require_POST
def api_run_embedding(request):
    task_id, task = _new_task("임베딩 (유사 시험 조회)")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _launch(
        [_VENV_PYTHON, "-u", "manage.py", "embed_db"],
        cwd=_CLAUDE_ROOT,
        env=env,
        task=task,
    )
    return JsonResponse({"task_id": task_id})


@csrf_exempt
@require_POST
def api_run_weekly(request):
    body = json.loads(request.body or b"{}")
    date = (body.get("date") or "").strip()
    task_id, task = _new_task("ECM 인증획득목록 동기화")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if date:
        env["GSCERT_WEEKLY_TARGET_DATE"] = date
    else:
        env.pop("GSCERT_WEEKLY_TARGET_DATE", None)
    _launch(
        [_VENV_PYTHON, "-u", r"C:\Claude_GSCert\main\utils\weekly.py"],
        cwd=_CLAUDE_ROOT,
        env=env,
        task=task,
    )
    return JsonResponse({"task_id": task_id})


@csrf_exempt
@require_POST
def api_run_sync_sheets(request):
    task_id, task = _new_task("Google Sheets 동기화")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _launch(
        [_VENV_PYTHON, "-u", "manage.py", "sync_reference_projects_from_sheet"],
        cwd=_CLAUDE_ROOT,
        env=env,
        task=task,
    )
    return JsonResponse({"task_id": task_id})


_POWERSHELL = "powershell.exe"


def _run_ps1(script_name: str, extra_args: list, task: dict):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    args = [
        _POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", os.path.join(_CLAUDE_ROOT, script_name),
    ] + extra_args
    _launch(args, cwd=_CLAUDE_ROOT, env=env, task=task)


@csrf_exempt
@require_POST
def api_run_worker(request):
    """다운로드 검토 워커를 시작한다(ECM HTTP 직접연동, source=ecm-http).

    start_worker.ps1 -Live -Source ecm-http 를 호출한다(백그라운드 기동 + PID 파일 관리).
    ps1 은 env.ps1 을 로드하므로 ECM 자격증명도 함께 적용된다.
    (레거시 Playwright 다운로드 방식은 제거됨.)
    """
    source = "ecm-http"
    task_id, task = _new_task("다운로드 워커 시작 (HTTP 직접연동)")
    _run_ps1("start_worker.ps1", ["-Live", "-Source", source], task)
    return JsonResponse({"task_id": task_id, "source": source})


@csrf_exempt
@require_POST
def api_stop_worker(request):
    """다운로드 검토 워커를 중지한다(stop_worker.ps1)."""
    task_id, task = _new_task("다운로드 워커 중지")
    _run_ps1("stop_worker.ps1", [], task)
    return JsonResponse({"task_id": task_id})


@require_GET
def api_task_status(request, task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        return JsonResponse({"error": "not found"}, status=404)
    offset = int(request.GET.get("offset", 0))
    new_lines = task["lines"][offset:]
    return JsonResponse({
        "status": task["status"],
        "lines": new_lines,
        "offset": offset + len(new_lines),
        "finished_at": task["finished_at"],
    })
