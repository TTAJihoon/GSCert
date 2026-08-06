import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-ui-mock-local-only"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "210.96.71.194", "210.96.71.241"]

ROOT_URLCONF = "myproject.ui_mock_urls"

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "main.apps.MainConfig",
]

MIDDLEWARE = [
    "main.request_logging.RequestLogMiddleware",
    "django.middleware.common.CommonMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "main" / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [],
        },
    },
]

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "main" / "static",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "workflow": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "main" / "data" / "workflow.db",
    },
    "reference": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "main" / "data" / "reference_mock.db",
    },
}

DATABASE_ROUTERS = [
    "main.db_routers.WorkflowDatabaseRouter",
    "main.db_routers.ReferenceDatabaseRouter",
]

WORKFLOW_DATABASE_ALIAS = "workflow"
WORKFLOW_MODEL_NAMES = {
    "downloadreviewjob",
    "downloadreviewproject",
    "downloadreviewrule",
    "downloadreviewruleresult",
    "downloadreviewlog",
    "downloadreviewlock",
    "servertimecontrol",
    "servertimeaudit",
}

SERVER_TIME_LEASE_SECONDS = 180
SERVER_TIME_NTP_HOST = "time.windows.com"
SERVER_TIME_VERIFY_TOLERANCE_SECONDS = 10

REFERENCE_DATABASE_ALIAS = "reference"
REFERENCE_MODEL_NAMES = {
    "swdata",
    "referencecenterpl",
    "referenceproject",
    "downloadreviewmanualoverride",
}
DOWNLOAD_REVIEW_PROJECT_SOURCE = "postgres"

ECM_AGENT_LOCK_PATH = BASE_DIR / "main" / "data" / "ecm_agent.lock"
ECM_AGENT_LOCK_TIMEOUT_SECONDS = 600
REFERENCE_DB_PATH = BASE_DIR / "main" / "data" / "ecmlist.db"
REFERENCE_DB_PATH_2 = BASE_DIR / "main" / "data" / "ecmlist2.db"
DOWNLOAD_REVIEW_ARTIFACT_DIR = BASE_DIR / "main" / "data" / "download_review_artifacts"
LOCAL_REVIEW_APP_PACKAGE_DIR = Path(
    os.environ.get(
        "LOCAL_REVIEW_APP_PACKAGE_DIR",
        r"C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard",
    )
)
LOCAL_REVIEW_APP_EXE_NAME = os.environ.get("LOCAL_REVIEW_APP_EXE_NAME", "GSCertLocalReviewDashboard.exe")
LOCAL_REVIEW_APP_ARCHIVE_NAME = os.environ.get("LOCAL_REVIEW_APP_ARCHIVE_NAME", "GSCertLocalReviewDashboard.zip")
REFERENCE_DB_TABLE = "ecm_list"
DOWNLOAD_REVIEW_DEFAULT_CENTER = "sangam"
DOWNLOAD_REVIEW_DEFAULT_CENTER_BY_HOST = {
    "210.96.71.194": "bundang",
    "210.96.71.241": "sangam",
}
DOWNLOAD_REVIEW_ALLOWED_CENTERS_BY_HOST = {
    "210.96.71.194": {"bundang"},
    "210.96.71.241": {"sangam", "yeongnam"},
}
DOWNLOAD_REVIEW_WORKER_CENTERS = {
    value.strip()
    for value in os.environ.get("DOWNLOAD_REVIEW_WORKER_CENTERS", "").split(",")
    if value.strip()
}
DOWNLOAD_REVIEW_CENTER_ROUTES_BY_HOST = {
    "210.96.71.194": {
        "bundang": "",
        "sangam": "http://210.96.71.241/download-review/",
        "yeongnam": "http://210.96.71.241/download-review/",
    },
    "210.96.71.241": {
        "bundang": "http://210.96.71.194/download-review/",
        "sangam": "",
        "yeongnam": "",
    },
}
DOWNLOAD_REVIEW_ACTIVE_JOB_LIMIT = 5
DOWNLOAD_REVIEW_MAX_PROJECTS_PER_JOB = 100
ECM_BASE_URL = os.environ.get("ECM_BASE_URL", "http://210.96.71.85")
ECM_BASE_URL_BUNDANG = os.environ.get("ECM_BASE_URL_BUNDANG", "http://210.104.181.10")
# HTTP 직접연동(ecm-http) 자격증명/ root OID — 환경변수로만 주입.
ECM_USERNAME = os.environ.get("ECM_USERNAME", "")
ECM_PASSWORD = os.environ.get("ECM_PASSWORD", "")
ECM_USERNAME_BUNDANG = os.environ.get("ECM_USERNAME_BUNDANG", "")
ECM_PASSWORD_BUNDANG = os.environ.get("ECM_PASSWORD_BUNDANG", "")
ECM_ROOT_OID_SANGAM = os.environ.get("ECM_ROOT_OID_SANGAM", "")
ECM_ROOT_OID_YEONGNAM = os.environ.get("ECM_ROOT_OID_YEONGNAM", "")
ECM_ROOT_OID_BUNDANG = os.environ.get("ECM_ROOT_OID_BUNDANG", "")
ECM_BROWSER_CHANNEL = os.environ.get("ECM_BROWSER_CHANNEL", "chrome")
ECM_BROWSER_ARGS = [
    arg.strip()
    for arg in os.environ.get(
        "ECM_BROWSER_ARGS",
        "--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults --disable-local-network-access-check",
    ).split()
    if arg.strip()
]
ECM_TREE_ROOT_INDEX = int(os.environ.get("ECM_TREE_ROOT_INDEX", "1"))
ECM_TREE_ROOT_INDEX_BUNDANG = int(os.environ.get("ECM_TREE_ROOT_INDEX_BUNDANG", "0"))
ECM_TREE_ROOT_INDEX_YEONGNAM = int(os.environ.get("ECM_TREE_ROOT_INDEX_YEONGNAM", "0"))
AGENT_DOWNLOAD_BASE_DIR = os.environ.get(
    "AGENT_DOWNLOAD_BASE_DIR",
    str(Path.home() / "Downloads"),
)
# 산출물 source 선택(main/docs/11_artifact_source_boundary.md 참고).
# 'ecm-http'(HTTP 직접연동, 기본) / 'local'(fake-live).
# 'local' + LOCAL_ARTIFACT_SOURCE_ROOT 로 ECM 없이 워커 흐름을 돌릴 수 있다(fake-live).
DOWNLOAD_REVIEW_SOURCE = os.environ.get("DOWNLOAD_REVIEW_SOURCE", "ecm-http")
LOCAL_ARTIFACT_SOURCE_ROOT = os.environ.get("LOCAL_ARTIFACT_SOURCE_ROOT", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "format": "%(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
        },
    },
    "loggers": {
        "gscert.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
