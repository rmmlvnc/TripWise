"""Private local credentials, with environment variables taking precedence."""
import json
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

path = Path(__file__).resolve().parent.parent / "api_credentials.json"
try:
    local = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(local, dict):
        raise ValueError("Expected object")
except (ValueError, OSError) as exc:
    raise ImproperlyConfigured("Fix api_credentials.json: it must contain a JSON object.") from None

GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", local.get("GEOAPIFY_API_KEY", ""))
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", local.get("CLOUDINARY_CLOUD_NAME", ""))
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", local.get("CLOUDINARY_API_KEY", ""))
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", local.get("CLOUDINARY_API_SECRET", ""))
