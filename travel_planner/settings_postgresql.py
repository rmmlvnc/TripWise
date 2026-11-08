"""PostgreSQL configuration. Set connection variables in your terminal first."""
import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *

if not os.environ.get("PGDATABASE") or not os.environ.get("PGUSER"):
    raise ImproperlyConfigured("Set PGDATABASE and PGUSER before using PostgreSQL settings.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["PGDATABASE"],
        "USER": os.environ["PGUSER"],
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", "127.0.0.1"),
        "PORT": os.environ.get("PGPORT", "5432"),
        "OPTIONS": {"sslmode": os.environ.get("PGSSLMODE", "prefer"), "connect_timeout": 10},
    }
}
