import os
from pathlib import Path

from dotenv import load_dotenv
from .aws_secrets import get_secret_string

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, ".env"))

def env(key, default=None):
    return os.environ.get(key, default)

SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "*").split(",")

SITE_BASE_URL = env("SITE_BASE_URL", "https://portal.cpdinclinic.com").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "accounts",
    "catalog",
    "publisher",
    "sharing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "peds_edu.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "peds_edu.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": env("DB_NAME", BASE_DIR / "db.sqlite3"),
        "USER": env("DB_USER", ""),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", ""),
        "PORT": env("DB_PORT", ""),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# SendGrid (Web API)
SENDGRID_API_KEY = env("SENDGRID_API_KEY", "").strip()
if not SENDGRID_API_KEY:
    # Fetch from AWS Secrets Manager (secret name: SendGrid_API)
    SENDGRID_API_KEY = (get_secret_string("SendGrid_API", region_name="ap-south-1") or "").strip()
SENDGRID_FROM_EMAIL = env("SENDGRID_FROM_EMAIL", "products@inditech.co.in").strip()

# Email backend selection (sendgrid = Web API; smtp = SMTP relay)
EMAIL_BACKEND_MODE = env("EMAIL_BACKEND_MODE", "smtp").strip().lower()

EMAIL_HOST = env("EMAIL_HOST", "smtp.sendgrid.net")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "apikey")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", SENDGRID_API_KEY)
DEFAULT_FROM_EMAIL = SENDGRID_FROM_EMAIL
