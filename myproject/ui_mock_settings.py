import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-ui-mock-local-only"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

ROOT_URLCONF = "myproject.ui_mock_urls"

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "main.apps.MainConfig",
]

MIDDLEWARE = [
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
}

DATABASE_ROUTERS = [
    "main.db_routers.WorkflowDatabaseRouter",
]

WORKFLOW_DATABASE_ALIAS = "workflow"
WORKFLOW_MODEL_NAMES = {
    "downloadreviewjob",
    "downloadreviewproject",
    "downloadreviewrule",
    "downloadreviewruleresult",
    "downloadreviewlog",
    "downloadreviewlock",
}

ECM_AGENT_LOCK_PATH = BASE_DIR / "main" / "data" / "ecm_agent.lock"
ECM_AGENT_LOCK_TIMEOUT_SECONDS = 600
REFERENCE_DB_PATH = BASE_DIR / "main" / "data" / "ecmlist.db"
REFERENCE_DB_TABLE = "ecm_list"
DOWNLOAD_REVIEW_TIME_ZONE = "Asia/Seoul"
# TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW):
# 라이브 검증 중에는 0~24 전체 시간 허용. 테스트 완료 즉시 START_HOUR=20, END_HOUR=7로 되돌린다.
DOWNLOAD_REVIEW_IGNORE_TIME_WINDOW = False
DOWNLOAD_REVIEW_START_HOUR = 0
DOWNLOAD_REVIEW_END_HOUR = 24
DOWNLOAD_REVIEW_ACTIVE_JOB_LIMIT = 5
DOWNLOAD_REVIEW_MAX_PROJECTS_PER_JOB = 100
ECM_BASE_URL = os.environ.get("ECM_BASE_URL", "http://210.96.71.85")
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
AGENT_DOWNLOAD_BASE_DIR = os.environ.get(
    "AGENT_DOWNLOAD_BASE_DIR",
    str(Path.home() / "Downloads"),
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
