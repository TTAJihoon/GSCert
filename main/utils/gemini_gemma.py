import json
import os
import re
import time

from dotenv import find_dotenv, load_dotenv


DEFAULT_GEMMA_MODEL = "gemma-4-26b-a4b-it"
DEFAULT_RETRY_COUNT = 1
DEFAULT_RETRY_DELAY_SECONDS = 0.8


class GemmaConfigError(RuntimeError):
    pass


class GemmaGenerationError(RuntimeError):
    pass


def _load_env():
    dotenv_path = find_dotenv(usecwd=True)
    load_dotenv(dotenv_path=dotenv_path or None)


def _split_models(value: str | None):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _model_candidates(primary_model: str, fallback_models=None):
    seen = set()
    candidates = []
    for candidate in [primary_model, *_split_models(fallback_models)]:
        if candidate and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)
    return candidates


def _is_retryable_error(exc: Exception) -> bool:
    text = str(exc).upper()
    return any(
        marker in text
        for marker in (
            "500",
            "502",
            "503",
            "504",
            "INTERNAL",
            "UNAVAILABLE",
            "DEADLINE",
            "RESOURCE_EXHAUSTED",
            "RATE_LIMIT",
        )
    )


def _format_generation_error(exc: Exception, model_name: str) -> str:
    return f"{model_name}: {exc}"


def generate_gemma_text(
    prompt: str,
    *,
    model: str | None = None,
    fallback_models=None,
    retries: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    _load_env()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    selected_model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMMA_MODEL

    if not api_key:
        raise GemmaConfigError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다.")

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
    except ImportError as exc:
        raise GemmaConfigError("google-genai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc

    last_error = None
    for candidate_model in _model_candidates(selected_model, fallback_models):
        for attempt in range(max(retries, 0) + 1):
            try:
                response = client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                )
                result_text = (getattr(response, "text", "") or "").strip()
                if not result_text:
                    raise GemmaGenerationError("Gemma 응답이 비어 있습니다.")
                return result_text
            except Exception as exc:
                last_error = exc
                if _is_retryable_error(exc) and attempt < max(retries, 0):
                    time.sleep(retry_delay)
                    continue
                break

    if last_error:
        raise GemmaGenerationError(
            _format_generation_error(last_error, candidate_model)
        ) from last_error
    raise GemmaGenerationError("Gemma 응답 생성에 실패했습니다.")


def generate_gemma_text_stream(
    prompt: str,
    *,
    model: str | None = None,
    fallback_models=None,
    retries: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
):
    _load_env()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    selected_model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMMA_MODEL

    if not api_key:
        raise GemmaConfigError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다.")

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
    except Exception as exc:
        if isinstance(exc, ImportError):
            raise GemmaConfigError("google-genai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc
        raise GemmaGenerationError(str(exc)) from exc

    last_error = None
    for candidate_model in _model_candidates(selected_model, fallback_models):
        for attempt in range(max(retries, 0) + 1):
            emitted = False
            try:
                stream = client.models.generate_content_stream(
                    model=candidate_model,
                    contents=prompt,
                )
                for chunk in stream:
                    text = (getattr(chunk, "text", "") or "")
                    if text:
                        emitted = True
                        yield text
                return
            except Exception as exc:
                last_error = exc
                if emitted:
                    raise GemmaGenerationError(
                        _format_generation_error(exc, candidate_model)
                    ) from exc
                if _is_retryable_error(exc) and attempt < max(retries, 0):
                    time.sleep(retry_delay)
                    continue
                break

    if last_error:
        raise GemmaGenerationError(
            _format_generation_error(last_error, candidate_model)
        ) from last_error
    raise GemmaGenerationError("Gemma 응답 생성에 실패했습니다.")


def extract_json_object(text: str):
    value = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1)
    else:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            value = value[start : end + 1]

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
