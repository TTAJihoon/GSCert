import json
import os
import re

from dotenv import load_dotenv


DEFAULT_GEMMA_MODEL = "gemma-4-26b-a4b-it"


class GemmaConfigError(RuntimeError):
    pass


class GemmaGenerationError(RuntimeError):
    pass


def generate_gemma_text(prompt: str, *, model: str | None = None) -> str:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    selected_model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMMA_MODEL

    if not api_key:
        raise GemmaConfigError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다.")

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=selected_model,
            contents=prompt,
        )
    except ImportError as exc:
        raise GemmaConfigError("google-genai 패키지가 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc
    except Exception as exc:
        raise GemmaGenerationError(str(exc)) from exc

    result_text = (getattr(response, "text", "") or "").strip()
    if not result_text:
        raise GemmaGenerationError("Gemma 응답이 비어 있습니다.")
    return result_text


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
