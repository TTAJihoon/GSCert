"""Runtime-selectable LLM model registry shared by API calls and server console."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import threading

from django.conf import settings


DEFAULT_MODEL_CATALOG = (
    "google:gemma-4-26b-a4b-it,"
    "google:gemini-3.5-flash-lite,"
    "openai:gpt-5.6-luna"
)
DEFAULT_ACTIVE_MODEL = "google:gemma-4-26b-a4b-it"
_STATE_LOCK = threading.Lock()


@dataclass(frozen=True)
class LlmModel:
    key: str
    provider: str
    model: str
    label: str
    available: bool
    active: bool = False

    def to_dict(self):
        return asdict(self)


def _state_path() -> Path:
    override = str(os.environ.get("GSCERT_LLM_STATE_FILE") or "").strip()
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / "run" / "llm_selection.json"


def _provider_available(provider: str) -> bool:
    if provider == "google":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    return False


def _label(provider: str, model: str) -> str:
    provider_label = {"google": "Google", "openai": "OpenAI"}.get(provider, provider)
    return f"{provider_label} / {model}"


def _catalog_keys() -> list[str]:
    raw = os.environ.get("GSCERT_LLM_MODELS") or DEFAULT_MODEL_CATALOG
    keys = []
    seen = set()
    for item in str(raw).split(","):
        key = item.strip()
        if ":" not in key:
            continue
        provider, model = key.split(":", 1)
        provider = provider.strip().lower()
        model = model.strip()
        normalized = f"{provider}:{model}"
        if provider not in {"google", "openai"} or not model or normalized in seen:
            continue
        keys.append(normalized)
        seen.add(normalized)
    return keys


def infer_provider(model: str) -> str:
    return "openai" if str(model or "").strip().lower().startswith("gpt-") else "google"


def _configured_default_key() -> str:
    explicit = str(os.environ.get("GSCERT_LLM_DEFAULT") or "").strip()
    if explicit:
        return explicit
    legacy_model = str(os.environ.get("GEMINI_MODEL") or "").strip()
    if legacy_model:
        return f"google:{legacy_model}"
    return DEFAULT_ACTIVE_MODEL


def _read_selected_key() -> str:
    path = _state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return str(payload.get("active_model") or "").strip()
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def get_active_model_key() -> str:
    catalog = _catalog_keys()
    selected = _read_selected_key()
    if selected in catalog and _provider_available(selected.split(":", 1)[0]):
        return selected

    configured = _configured_default_key()
    if configured in catalog and _provider_available(configured.split(":", 1)[0]):
        return configured

    for key in catalog:
        if _provider_available(key.split(":", 1)[0]):
            return key
    return configured if configured in catalog else (catalog[0] if catalog else DEFAULT_ACTIVE_MODEL)


def get_active_model() -> tuple[str, str]:
    key = get_active_model_key()
    provider, model = key.split(":", 1)
    return provider, model


def list_llm_models() -> list[dict]:
    active_key = get_active_model_key()
    return [
        LlmModel(
            key=key,
            provider=key.split(":", 1)[0],
            model=key.split(":", 1)[1],
            label=_label(*key.split(":", 1)),
            available=_provider_available(key.split(":", 1)[0]),
            active=key == active_key,
        ).to_dict()
        for key in _catalog_keys()
    ]


def select_llm_model(key: str) -> dict:
    normalized = str(key or "").strip()
    catalog = _catalog_keys()
    if normalized not in catalog:
        raise ValueError("등록되지 않은 LLM 모델입니다.")
    provider, model = normalized.split(":", 1)
    if not _provider_available(provider):
        variable = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
        raise ValueError(f"{variable} 환경변수가 설정되지 않아 선택할 수 없습니다.")

    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {"active_model": normalized}
    with _STATE_LOCK:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    return {
        "key": normalized,
        "provider": provider,
        "model": model,
        "label": _label(provider, model),
    }
