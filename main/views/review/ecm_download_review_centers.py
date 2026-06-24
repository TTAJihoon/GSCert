from pathlib import Path
import socket
from urllib.parse import urlparse

from django.conf import settings


CENTER_SANGAM = "sangam"
CENTER_BUNDANG = "bundang"
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
    CENTER_BUNDANG: {
        "label": "분당",
        "reference_db_setting": "REFERENCE_DB_PATH_BUNDANG",
        "default_db_name": "ecmlist_bundang.db",
        "tree_root": "분당AX센터",
        "tree_root_index_setting": "ECM_TREE_ROOT_INDEX_BUNDANG",
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


def default_center_for_host(host=None):
    configured = getattr(settings, "DOWNLOAD_REVIEW_DEFAULT_CENTER_BY_HOST", {})
    host_key = _host_key(host)
    if host_key and host_key in configured:
        return normalize_center_code(configured[host_key])
    return normalize_center_code(None)


def allowed_centers_for_host(host=None):
    configured = getattr(settings, "DOWNLOAD_REVIEW_ALLOWED_CENTERS_BY_HOST", {})
    host_key = _host_key(host)
    values = configured.get(host_key) if host_key else None
    if not values:
        return set(_CENTER_DEFINITIONS)
    return {normalize_center_code(value) for value in values}


def is_center_allowed_for_host(center_code, host=None):
    return normalize_center_code(center_code) in allowed_centers_for_host(host)


def center_routes_for_host(host=None):
    configured = getattr(settings, "DOWNLOAD_REVIEW_CENTER_ROUTES_BY_HOST", {})
    host_key = _host_key(host)
    routes = configured.get(host_key, {}) if host_key else {}
    return {
        normalize_center_code(center): str(url or "")
        for center, url in routes.items()
    }


def worker_allowed_centers():
    configured = getattr(settings, "DOWNLOAD_REVIEW_WORKER_CENTERS", None)
    if configured:
        return {normalize_center_code(value) for value in configured}

    host_map = getattr(settings, "DOWNLOAD_REVIEW_ALLOWED_CENTERS_BY_HOST", {})
    local_hosts = _local_host_keys()
    for host in local_hosts:
        if host in host_map:
            return {normalize_center_code(value) for value in host_map[host]}
    return set(_CENTER_DEFINITIONS)


def normalize_center_code(value=None):
    center = str(value or "").strip().lower()
    if not center:
        return getattr(settings, "DOWNLOAD_REVIEW_DEFAULT_CENTER", DEFAULT_CENTER_CODE)
    aliases = {
        "상암": CENTER_SANGAM,
        "sangam": CENTER_SANGAM,
        "bundang": CENTER_BUNDANG,
        "분당": CENTER_BUNDANG,
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


def _host_key(host=None):
    if not host:
        return ""
    raw = str(host).strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlparse(raw)
        raw = parsed.netloc or parsed.path
    if raw.startswith("[") and "]" in raw:
        return raw[1:raw.index("]")]
    return raw.split(":", 1)[0]


def _local_host_keys():
    hosts = {"localhost", "127.0.0.1"}
    try:
        hostname = socket.gethostname()
        hosts.add(hostname.lower())
        for info in socket.getaddrinfo(hostname, None):
            address = info[4][0]
            if address:
                hosts.add(_host_key(address))
    except OSError:
        pass
    return hosts
