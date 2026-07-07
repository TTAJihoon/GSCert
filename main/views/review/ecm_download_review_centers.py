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
        "ecm_url_setting": "ECM_BASE_URL",
        "default_ecm_base_url": "http://210.96.71.85",
        # HTTP 직접연동(ecm-http): root OID + 자격증명 설정 키. 상암·영남은 같은
        # 서버(210.96.71.85)를 공유하고 계정도 공유(ECM_USERNAME/ECM_PASSWORD)한다.
        "ecm_root_oid_setting": "ECM_ROOT_OID_SANGAM",
        "default_ecm_root_oid": "1PQSYcuFhzv",
        "username_setting": "ECM_USERNAME",
        "password_setting": "ECM_PASSWORD",
    },
    CENTER_BUNDANG: {
        "label": "분당",
        "reference_db_setting": "REFERENCE_DB_PATH_BUNDANG",
        "default_db_name": "ecmlist_bundang.db",
        "tree_root": "",
        "tree_root_index_setting": "ECM_TREE_ROOT_INDEX_BUNDANG",
        "default_tree_root_index": 0,
        "test_type_contains": "GS 시험인증(1등급)",
        "ecm_url_setting": "ECM_BASE_URL_BUNDANG",
        "default_ecm_base_url": "http://210.104.181.10",
        # 분당은 별도 서버(210.104.181.10) + 별도 계정.
        "ecm_root_oid_setting": "ECM_ROOT_OID_BUNDANG",
        "default_ecm_root_oid": "C_ROOT",
        "username_setting": "ECM_USERNAME_BUNDANG",
        "password_setting": "ECM_PASSWORD_BUNDANG",
    },
    CENTER_YEONGNAM: {
        "label": "영남",
        "reference_db_setting": "REFERENCE_DB_PATH_2",
        "default_db_name": "ecmlist2.db",
        "tree_root": "영남AX센터",
        "tree_root_index_setting": "ECM_TREE_ROOT_INDEX_YEONGNAM",
        "default_tree_root_index": 0,
        "test_type_label": "01 GS시험인증(1등급)",
        "ecm_url_setting": "ECM_BASE_URL",
        "default_ecm_base_url": "http://210.96.71.85",
        # 영남은 상암과 같은 서버·계정을 공유하고 최상위 폴더 OID로만 구분한다.
        "ecm_root_oid_setting": "ECM_ROOT_OID_YEONGNAM",
        "default_ecm_root_oid": "1EBnGfHdFwe",
        "username_setting": "ECM_USERNAME",
        "password_setting": "ECM_PASSWORD",
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


def ecm_has_tree_root(center_code):
    return bool(ecm_tree_root(center_code))


def ecm_tree_root_index(center_code):
    definition = _definition(center_code)
    return int(
        getattr(
            settings,
            definition["tree_root_index_setting"],
            definition["default_tree_root_index"],
        )
    )


def ecm_base_url(center_code=""):
    definition = _definition(center_code)
    configured = getattr(settings, definition["ecm_url_setting"], None)
    if configured:
        return str(configured)
    return definition["default_ecm_base_url"]


def ecm_root_oid(center_code=""):
    """HTTP 직접연동 트리 탐색 시작 폴더 OID. 설정으로 덮어쓸 수 있고 없으면 기본값."""
    definition = _definition(center_code)
    configured = getattr(settings, definition["ecm_root_oid_setting"], None)
    if configured:
        return str(configured)
    return definition["default_ecm_root_oid"]


def ecm_credentials(center_code=""):
    """HTTP 직접연동 로그인용 (username, password). 환경변수(settings)에서만 읽는다.

    상암·영남은 같은 설정 키(ECM_USERNAME/ECM_PASSWORD)를 가리켜 계정을 공유한다.
    코드/DB 에 평문을 저장하지 않으므로, 미설정 시 빈 문자열을 돌려준다(호출부에서 판단).
    """
    definition = _definition(center_code)
    username = getattr(settings, definition["username_setting"], "") or ""
    password = getattr(settings, definition["password_setting"], "") or ""
    return str(username), str(password)


def ecm_test_type_label(center_code):
    return _definition(center_code).get("test_type_label", "01 GS인증시험(1등급)")


def ecm_test_type_contains(center_code):
    return _definition(center_code).get("test_type_contains", ecm_test_type_label(center_code))


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
