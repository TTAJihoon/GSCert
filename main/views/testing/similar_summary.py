from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import logging
import os
import re
import shutil
import uuid
from datetime import date, timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from main.models import SimilarAnalysisJob
from main.request_logging import set_request_log_context
from main.utils.gemini_gemma import GemmaConfigError, GemmaGenerationError
from .similar_analysis import analyze_documents
from .similar_documents import (
    DocumentParseError,
    SUPPORTED_EXTENSIONS,
    parse_document,
    save_uploaded_file,
)
from .similar_GPT import (
    generate_recommended_summaries,
    rerank_multiple_similar_candidates,
    run_gemini_gemma,
)
from .similar_compare import (
    SimilarSearchDependencyError,
    compare_multiple_from_index,
)

logger = logging.getLogger(__name__)


def parse_file(uploaded_file):
    """Backward-compatible single-file helper used by existing callers/tests."""
    suffix = Path(uploaded_file.name).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name
    try:
        return parse_document(tmp_path, uploaded_file.name).text
    except DocumentParseError:
        return None
    finally:
        os.unlink(tmp_path)


# 텍스트 전처리 (공백 및 줄바꿈 제거)
def preprocess_text(text):
    return " ".join(str(text or "").split())


_analysis_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="similar-analysis")


def _safe_upload_name(index, original_name):
    extension = Path(original_name).suffix.lower()
    return f"{index:04d}-{uuid.uuid4().hex}{extension}"


def _analysis_job_payload(job):
    payload = {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "progress_message": job.progress_message,
    }
    if job.status == SimilarAnalysisJob.Status.COMPLETED:
        payload.update(job.result_json)
    elif job.status == SimilarAnalysisJob.Status.FAILED:
        payload["response"] = job.error_message or "문서 분석에 실패했습니다."
    return payload


def _run_analysis_job(job_id):
    job = SimilarAnalysisJob.objects.get(id=job_id)
    job.status = SimilarAnalysisJob.Status.RUNNING
    job.started_at = timezone.now()
    job.progress = 2
    job.progress_message = "업로드 파일을 확인하고 있습니다."
    job.save(update_fields=["status", "started_at", "progress", "progress_message", "updated_at"])

    documents = []
    file_reports = []
    try:
        files = job.input_files_json
        for index, item in enumerate(files, 1):
            progress = 5 + int((index - 1) / max(len(files), 1) * 65)
            job.progress = progress
            job.progress_message = f"{item['name']} 텍스트를 추출하고 있습니다."
            job.save(update_fields=["progress", "progress_message", "updated_at"])
            try:
                parsed = parse_document(item["path"], item["name"])
                documents.append(parsed)
                file_reports.append(
                    {
                        "name": item["name"],
                        "status": "parsed",
                        "units": len(parsed.units),
                        "warnings": parsed.warnings,
                        "stats": parsed.stats,
                    }
                )
            except Exception as exc:
                if not isinstance(exc, DocumentParseError):
                    logger.exception("Similar document parse failed: %s", item["name"])
                safe_error = (
                    str(exc)
                    if isinstance(exc, DocumentParseError)
                    else "파일 내용을 읽지 못했습니다."
                )
                file_reports.append(
                    {"name": item["name"], "status": "failed", "error": safe_error}
                )

        if not documents:
            details = "; ".join(
                f"{item['name']}: {item.get('error', '분석 실패')}" for item in file_reports
            )
            raise DocumentParseError(f"분석 가능한 파일이 없습니다. {details}")

        job.progress = 75
        job.progress_message = "추출 내용을 정리하고 제품 개요를 생성하고 있습니다."
        job.save(update_fields=["progress", "progress_message", "updated_at"])
        original, recommendations, coverage = analyze_documents(
            documents,
            failed_files=len(files) - len(documents),
            max_chars=60,
        )
        options = [
            {
                "id": f"recommendation-{index + 1}",
                "text": summary,
                "is_original": False,
            }
            for index, summary in enumerate(recommendations)
        ]
        options.append({"id": "original", "text": original, "is_original": True})
        job.result_json = {
            "mode": "file",
            "options": options,
            "default_selected_ids": ["recommendation-1"],
            "file_reports": file_reports,
            "coverage": coverage.to_dict(),
        }
        job.status = SimilarAnalysisJob.Status.COMPLETED
        job.progress = 100
        job.progress_message = "제품 개요 후보 생성이 완료되었습니다."
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "result_json",
                "status",
                "progress",
                "progress_message",
                "completed_at",
                "updated_at",
            ]
        )
    except Exception as exc:
        logger.exception("Similar analysis job failed: %s", job_id)
        job.status = SimilarAnalysisJob.Status.FAILED
        if isinstance(
            exc,
            (DocumentParseError, GemmaConfigError, GemmaGenerationError),
        ):
            job.error_message = str(exc)
        else:
            job.error_message = "문서 분석 중 예기치 않은 오류가 발생했습니다."
        job.progress_message = "문서 분석에 실패했습니다."
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_message",
                "progress_message",
                "completed_at",
                "updated_at",
            ]
        )
    finally:
        shutil.rmtree(Path(settings.SIMILAR_ANALYSIS_DIR) / str(job.id), ignore_errors=True)


def _start_file_analysis(request):
    uploaded_files = request.FILES.getlist("file")
    if not uploaded_files:
        return JsonResponse({"response": "분석할 파일을 하나 이상 선택해주세요."}, status=400)
    total_size = sum(file.size for file in uploaded_files)
    if total_size > settings.SIMILAR_UPLOAD_TOTAL_LIMIT_BYTES:
        return JsonResponse(
            {"response": "한 번에 업로드할 수 있는 전체 용량은 200MB입니다."},
            status=413,
        )
    invalid = [
        file.name
        for file in uploaded_files
        if Path(file.name).suffix.lower() not in SUPPORTED_EXTENSIONS
    ]
    oversized = [
        file.name
        for file in uploaded_files
        if file.size > settings.SIMILAR_UPLOAD_FILE_LIMIT_BYTES
    ]
    if invalid:
        return JsonResponse(
            {
                "response": (
                    "지원 형식은 pdf, doc(x), xls(x), hwp(x), ppt(x), md입니다: "
                    + ", ".join(invalid[:10])
                )
            },
            status=400,
        )
    if oversized:
        return JsonResponse(
            {"response": "파일당 최대 용량은 100MB입니다: " + ", ".join(oversized[:10])},
            status=413,
        )

    SimilarAnalysisJob.objects.filter(
        completed_at__lt=timezone.now() - timedelta(days=7)
    ).delete()
    job = SimilarAnalysisJob.objects.create(
        progress_message="업로드 파일을 저장하고 있습니다."
    )
    job_dir = Path(settings.SIMILAR_ANALYSIS_DIR) / str(job.id)
    stored = []
    try:
        for index, uploaded_file in enumerate(uploaded_files, 1):
            destination = job_dir / _safe_upload_name(index, uploaded_file.name)
            save_uploaded_file(uploaded_file, destination)
            stored.append(
                {"name": Path(uploaded_file.name).name, "path": str(destination)}
            )
        job.input_files_json = stored
        job.save(update_fields=["input_files_json", "updated_at"])
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        job.delete()
        raise

    set_request_log_context(
        request,
        feature="similar",
        input_mode="file",
        file_type=request.POST.get("fileType", ""),
        file_name=", ".join(item["name"] for item in stored),
    )
    _analysis_executor.submit(_run_analysis_job, job.id)
    return JsonResponse(_analysis_job_payload(job), status=202)


def _get_analysis_status(request):
    job_id = request.POST.get("jobId", "").strip()
    try:
        job = SimilarAnalysisJob.objects.get(id=job_id)
    except (ValueError, SimilarAnalysisJob.DoesNotExist):
        return JsonResponse({"response": "분석 작업을 찾을 수 없습니다."}, status=404)
    if (
        job.status in {SimilarAnalysisJob.Status.QUEUED, SimilarAnalysisJob.Status.RUNNING}
        and job.updated_at < timezone.now() - timedelta(minutes=30)
    ):
        job.status = SimilarAnalysisJob.Status.FAILED
        job.error_message = "서버 재시작 또는 제한 시간 초과로 분석 작업이 중단되었습니다."
        job.progress_message = "문서 분석 작업이 중단되었습니다."
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_message",
                "progress_message",
                "completed_at",
                "updated_at",
            ]
        )
        shutil.rmtree(
            Path(settings.SIMILAR_ANALYSIS_DIR) / str(job.id),
            ignore_errors=True,
        )
    return JsonResponse(_analysis_job_payload(job))


def _prepare_summary_options(request):
    file_type = request.POST.get("fileType", "")
    uploaded_file = request.FILES.get("file")
    manual_input = request.POST.get("manualInput", "").strip()

    if uploaded_file:
        set_request_log_context(
            request,
            feature="similar",
            input_mode="file",
            file_type=file_type,
            file_name=uploaded_file.name,
        )
        text = parse_file(uploaded_file)
        if text is None or len(text.strip()) < 10:
            return JsonResponse(
                {"response": "내용이 부족하거나 지원되지 않는 형식입니다."},
                status=400,
            )

        clean_text = preprocess_text(text)
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        original_summary = preprocess_text(run_gemini_gemma(sentences))
        if original_summary.startswith("❌"):
            return JsonResponse({"response": original_summary}, status=503)

        try:
            recommendations = generate_recommended_summaries(
                clean_text,
                count=4,
                max_chars=60,
            )
        except (GemmaConfigError, GemmaGenerationError) as exc:
            return JsonResponse(
                {"response": f"추천 요약 문장을 생성하지 못했습니다: {exc}"},
                status=503,
            )

        options = [
            {
                "id": f"recommendation-{index + 1}",
                "text": summary,
                "is_original": False,
            }
            for index, summary in enumerate(recommendations)
        ]
        options.append(
            {
                "id": "original",
                "text": original_summary,
                "is_original": True,
            }
        )
        default_selected_ids = ["recommendation-1"]
        set_request_log_context(request, llm_summary=original_summary)
        input_mode = "file"
    elif manual_input:
        original_summary = preprocess_text(manual_input)
        set_request_log_context(
            request,
            feature="similar",
            input_mode="manual",
            manual_input=manual_input,
        )
        try:
            recommendations = generate_recommended_summaries(
                original_summary,
                count=5,
                max_chars=60,
            )
        except (GemmaConfigError, GemmaGenerationError) as exc:
            return JsonResponse(
                {"response": f"추천 제품 개요 문장을 생성하지 못했습니다: {exc}"},
                status=503,
            )

        options = [
            {
                "id": f"recommendation-{index + 1}",
                "text": summary,
                "is_original": False,
            }
            for index, summary in enumerate(recommendations)
        ]
        options.append(
            {
                "id": "original",
                "text": original_summary,
                "is_original": True,
            }
        )
        default_selected_ids = ["original"]
        input_mode = "manual"
    else:
        set_request_log_context(request, feature="similar", input_mode="empty")
        return JsonResponse(
            {"response": "파일 또는 제품 설명을 입력해주세요."},
            status=400,
        )

    return JsonResponse(
        {
            "mode": input_mode,
            "options": options,
            "default_selected_ids": default_selected_ids,
        }
    )


def _parse_selected_summaries(request):
    raw_value = request.POST.get("selectedSummaries", "")
    try:
        values = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(values, list):
        return None

    selected = []
    seen = set()
    for value in values:
        summary = preprocess_text(str(value or ""))
        if not summary or summary in seen:
            continue
        if len(summary) > 10000:
            return None
        selected.append(summary)
        seen.add(summary)
    if not 1 <= len(selected) <= 6:
        return None
    return selected


def _parse_search_period(request):
    raw_start = request.POST.get("searchStartDate", "").strip() or "2017-01-01"
    raw_end = request.POST.get("searchEndDate", "").strip() or date.today().isoformat()
    try:
        start_date = date.fromisoformat(raw_start)
        end_date = date.fromisoformat(raw_end)
    except ValueError:
        return None
    if start_date > end_date:
        return None
    return start_date, end_date


def _search_selected_summaries(request):
    selected_summaries = _parse_selected_summaries(request)
    if not selected_summaries:
        return JsonResponse(
            {"response": "유사도를 판단할 문장을 1개 이상 선택해주세요."},
            status=400,
        )

    search_period = _parse_search_period(request)
    if not search_period:
        return JsonResponse(
            {"response": "인증일자 검색 기간을 올바르게 입력해주세요."},
            status=400,
        )
    cert_date_from, cert_date_to = search_period

    set_request_log_context(
        request,
        feature="similar",
        input_mode=request.POST.get("inputMode", ""),
        search_query=" | ".join(selected_summaries),
    )

    try:
        faiss_result, _ = compare_multiple_from_index(
            selected_summaries,
            k=30,
            cert_date_from=cert_date_from,
            cert_date_to=cert_date_to,
        )
    except SimilarSearchDependencyError as exc:
        return JsonResponse({"response": str(exc)}, status=503)

    rerank_error = ""
    try:
        compare_result = rerank_multiple_similar_candidates(
            selected_summaries,
            faiss_result,
        )
        if not compare_result:
            rerank_error = "LLM 재평가 결과가 비어 있어 FAISS 평균 결과를 표시합니다."
            compare_result = faiss_result
    except (GemmaConfigError, GemmaGenerationError) as exc:
        rerank_error = f"LLM 재평가를 수행하지 못해 FAISS 평균 결과를 표시합니다: {exc}"
        compare_result = faiss_result

    for row in compare_result:
        row.pop("faiss_scores", None)

    similarity_list = [row.get("similarity", 0.0) for row in compare_result]
    set_request_log_context(request, result_count=len(compare_result))
    return JsonResponse(
        {
            "summary": selected_summaries,
            "response": compare_result,
            "similarities": similarity_list,
            "rerank_error": rerank_error,
            "search_period": {
                "start": cert_date_from.isoformat(),
                "end": cert_date_to.isoformat(),
            },
        }
    )


# Django 뷰 함수 (추천 문장 준비 + 선택 문장 검색 API)
@csrf_exempt
def summarize_document(request):
    if request.method != "POST":
        return JsonResponse(
            {"response": "POST 메소드만 지원됩니다."},
            status=405,
        )

    action = request.POST.get("action", "prepare")
    if action == "prepare_async":
        return _start_file_analysis(request)
    if action == "status":
        return _get_analysis_status(request)
    if action == "prepare":
        return _prepare_summary_options(request)
    if action == "search":
        return _search_selected_summaries(request)
    return JsonResponse({"response": "지원하지 않는 요청입니다."}, status=400)
