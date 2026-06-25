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
