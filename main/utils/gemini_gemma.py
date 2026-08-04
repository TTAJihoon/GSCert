import json
import os
import re
import time

from dotenv import find_dotenv, load_dotenv

from main.utils.llm_models import get_active_model, infer_provider


DEFAULT_RETRY_COUNT = 1
DEFAULT_RETRY_DELAY_SECONDS = 0.8


class GemmaConfigError(RuntimeError):
    pass


class GemmaGenerationError(RuntimeError):
    pass


class GemmaRateLimitError(GemmaGenerationError):
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
        )
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).upper()
    return any(
        marker in text
        for marker in (
            "429",
            "RESOURCE_EXHAUSTED",
            "RATE_LIMIT",
            "RATE LIMIT",
            "QUOTA",
            "TOO MANY REQUESTS",
            "EXCEEDED",
            "REQUESTS PER MINUTE",
            "TOKENS PER MINUTE",
        )
    )


def _format_generation_error(exc: Exception, model_name: str) -> str:
    return f"{model_name}: {exc}"


def _resolve_model(model: str | None) -> tuple[str, str]:
    if model:
        value = str(model).strip()
        if ":" in value and value.split(":", 1)[0] in {"google", "openai"}:
            return tuple(value.split(":", 1))
        return infer_provider(value), value
    return get_active_model()


def _candidate_route(candidate: str) -> tuple[str, str]:
    value = str(candidate or "").strip()
    if ":" in value and value.split(":", 1)[0] in {"google", "openai"}:
        return tuple(value.split(":", 1))
    return infer_provider(value), value


def _usage_payload(usage, model_name: str, provider: str) -> dict:
    if provider == "openai":
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    else:
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        total_tokens = int(getattr(usage, "total_token_count", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "model": model_name,
        "provider": provider,
    }


def _generate_google_text(prompt: str, model_name: str):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise GemmaConfigError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다.")
    try:
        from google import genai
    except ImportError as exc:
        raise GemmaConfigError(
            "google-genai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요."
        ) from exc
    response = genai.Client(api_key=api_key).models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return (getattr(response, "text", "") or "").strip(), getattr(
        response, "usage_metadata", None
    )


def _openai_request_options(model_name: str) -> dict:
    options = {"model": model_name}
    if model_name.startswith("gpt-5.6"):
        options["reasoning"] = {
            "effort": os.environ.get("OPENAI_REASONING_EFFORT") or "low"
        }
    return options


def _generate_openai_text(prompt: str, model_name: str):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise GemmaConfigError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise GemmaConfigError(
            "openai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요."
        ) from exc
    response = OpenAI(api_key=api_key).responses.create(
        input=prompt,
        **_openai_request_options(model_name),
    )
    return (getattr(response, "output_text", "") or "").strip(), getattr(
        response, "usage", None
    )


def generate_gemma_text(
    prompt: str,
    *,
    model: str | None = None,
    fallback_models=None,
    retries: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    usage_callback=None,
) -> str:
    _load_env()
    selected_provider, selected_model = _resolve_model(model)

    last_error = None
    selected_candidate = f"{selected_provider}:{selected_model}"
    for candidate in _model_candidates(selected_candidate, fallback_models):
        provider, candidate_model = _candidate_route(candidate)
        for attempt in range(max(retries, 0) + 1):
            try:
                if provider == "openai":
                    result_text, usage = _generate_openai_text(prompt, candidate_model)
                else:
                    result_text, usage = _generate_google_text(prompt, candidate_model)
                if not result_text:
                    raise GemmaGenerationError("LLM 응답이 비어 있습니다.")
                if usage_callback:
                    try:
                        usage_callback(_usage_payload(usage, candidate_model, provider))
                    except Exception:
                        # Usage telemetry must never turn a successful generation
                        # into a user-visible failure.
                        pass
                return result_text
            except Exception as exc:
                last_error = exc
                if _is_rate_limit_error(exc):
                    raise GemmaRateLimitError(
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
    raise GemmaGenerationError("LLM 응답 생성에 실패했습니다.")


def count_gemma_tokens(
    contents: str,
    *,
    model: str | None = None,
) -> int:
    """Return the provider token count, falling back to a conservative estimate."""
    text = str(contents or "")
    if not text:
        return 0
    _load_env()
    provider, selected_model = _resolve_model(model)
    if provider == "openai":
        return max(1, (len(text) + 3) // 4)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return max(1, (len(text) + 3) // 4)
    try:
        from google import genai

        response = genai.Client(api_key=api_key).models.count_tokens(
            model=selected_model,
            contents=text,
        )
        return int(getattr(response, "total_tokens", 0) or 0)
    except Exception:
        return max(1, (len(text) + 3) // 4)


def generate_gemma_text_stream(
    prompt: str,
    *,
    model: str | None = None,
    fallback_models=None,
    retries: int = DEFAULT_RETRY_COUNT,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
):
    _load_env()
    selected_provider, selected_model = _resolve_model(model)

    last_error = None
    selected_candidate = f"{selected_provider}:{selected_model}"
    for candidate in _model_candidates(selected_candidate, fallback_models):
        provider, candidate_model = _candidate_route(candidate)
        for attempt in range(max(retries, 0) + 1):
            emitted = False
            try:
                if provider == "openai":
                    api_key = os.environ.get("OPENAI_API_KEY")
                    if not api_key:
                        raise GemmaConfigError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
                    try:
                        from openai import OpenAI
                    except ImportError as exc:
                        raise GemmaConfigError(
                            "openai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요."
                        ) from exc
                    with OpenAI(api_key=api_key).responses.stream(
                        input=prompt,
                        **_openai_request_options(candidate_model),
                    ) as stream:
                        for event in stream:
                            if getattr(event, "type", "") != "response.output_text.delta":
                                continue
                            text = getattr(event, "delta", "") or ""
                            if text:
                                emitted = True
                                yield text
                else:
                    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                    if not api_key:
                        raise GemmaConfigError(
                            "GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다."
                        )
                    try:
                        from google import genai
                    except ImportError as exc:
                        raise GemmaConfigError(
                            "google-genai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요."
                        ) from exc
                    stream = genai.Client(api_key=api_key).models.generate_content_stream(
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
                if _is_rate_limit_error(exc):
                    raise GemmaRateLimitError(
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
    raise GemmaGenerationError("LLM 응답 생성에 실패했습니다.")


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
