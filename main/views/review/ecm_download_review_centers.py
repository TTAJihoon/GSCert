from pathlib import Path

from django.conf import settings


CENTER_SANGAM = "sangam"
CENTER_YEONGNAM = "yeongnam"
DEFAULT_CENTER_CODE = CENTER_SANGAM

_CENTER_DEFINITIONS = {
    CENTER_SANGAM: {
        "label": "상암",
        "reference_db_setting": "REFERENCE_DB_PATH",
        "default_db_name": "ecmlist.db",
        "tree_root": "상암AX센터",
        "tree_root_index_setting": "ECM_TREE_ROOT_INDEX",
        "default_tree_root_index": 0,
    },
    CENTER_YEONGNAM: {
        "label": "영남",
        "reference_db_setting": "REFERENCE_DB_PATH_2",
        "default_db_name": "ecmlist2.db",
        "tree_root": "영남AX센터",
        "tree_root_index_setting": "ECM_TREE_ROOT_INDEX_YEONGNAM",
        "default_tree_root_index": 0,
    },
}


class DownloadReviewCenterError(ValueError):
    error_code = "invalid_center"


def center_choices():
    return [
        {"code": code, "label": definition["label"]}
        for code, definition in _CENTER_DEFINITIONS.items()
    ]


def normalize_center_code(value=None):
    center = str(value or "").strip().lower()
    if not center:
        return getattr(settings, "DOWNLOAD_REVIEW_DEFAULT_CENTER", DEFAULT_CENTER_CODE)
    aliases = {
        "상암": CENTER_SANGAM,
        "sangam": CENTER_SANGAM,
        "yeongnam": CENTER_YEONGNAM,
        "영남": CENTER_YEONGNAM,
    }
    normalized = aliases.get(center, center)
    if normalized not in _CENTER_DEFINITIONS:
        raise DownloadReviewCenterError(f"지원하지 않는 센터입니다: {value}")
    return normalized


def center_label(center_code):
    return _definition(center_code)["label"]


def reference_db_path(center_code):
    definition = _definition(center_code)
    configured = getattr(settings, definition["reference_db_setting"], None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "main" / "data" / definition["default_db_name"]


def ecm_tree_root(center_code):
    return _definition(center_code)["tree_root"]


def ecm_tree_root_index(center_code):
    definition = _definition(center_code)
    return int(
        getattr(
            settings,
            definition["tree_root_index_setting"],
            definition["default_tree_root_index"],
        )
    )


def _definition(center_code):
    normalized = normalize_center_code(center_code)
    return _CENTER_DEFINITIONS[normalized]
