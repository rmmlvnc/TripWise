"""Render-only configuration; local development settings are unchanged."""
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from .settings import *

DEBUG = False
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Set SECRET_KEY to a new random value of at least 50 characters in Render.")

ALLOWED_HOSTS = [value.strip() for value in os.environ.get("ALLOWED_HOSTS", "").split(",") if value.strip()]
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Configure RENDER_EXTERNAL_HOSTNAME or explicit ALLOWED_HOSTS for production.")
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    raise ImproperlyConfigured("Set DATABASE_URL to your hosted PostgreSQL connection URL in Render.")
try:
    database = dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True, ssl_require=True)
except Exception:
    raise ImproperlyConfigured("DATABASE_URL must be a valid PostgreSQL connection URL.") from None
if database["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
database.setdefault("OPTIONS", {})["connect_timeout"] = 10
DATABASES = {"default": database}

MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_KEEP_ONLY_HASHED_FILES = True

# Render terminates TLS and forwards the original protocol to Django.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 3600

# Production must use Render environment values, never a local credential file.
GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "").strip()
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()
