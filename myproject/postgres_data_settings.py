import os

from .ui_mock_settings import *  # noqa: F401,F403


def _postgres_database_config():
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("GSCERT_DB_NAME", "gscert_prod"),
        "USER": os.environ.get("GSCERT_DB_USER", "gscert_app"),
        "PASSWORD": os.environ.get("GSCERT_DB_PASSWORD", ""),
        "HOST": os.environ.get("GSCERT_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("GSCERT_DB_PORT", "5432"),
    }

    sslmode = os.environ.get("GSCERT_DB_SSLMODE")
    if sslmode:
        config["OPTIONS"] = {"sslmode": sslmode}
    return config


_POSTGRES_DATABASE = _postgres_database_config()

DATABASES = {
    "default": _POSTGRES_DATABASE.copy(),
    "reference": _POSTGRES_DATABASE.copy(),
}

DATABASE_ROUTERS = [
    "main.db_routers.ReferenceDatabaseRouter",
]

REFERENCE_DATABASE_ALIAS = "reference"
REFERENCE_MODEL_NAMES = {"swdata", "referencecenterpl", "referenceproject"}
DOWNLOAD_REVIEW_PROJECT_SOURCE = os.environ.get("DOWNLOAD_REVIEW_PROJECT_SOURCE", "postgres")
