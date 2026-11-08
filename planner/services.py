"""Server-side external APIs. No credentials are sent to the browser."""
import hashlib
import math
import re
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
import requests
from django.conf import settings
from django.core.cache import cache


class APIError(Exception):
    pass


CURRENCIES = ("USD", "EUR", "JPY", "GBP", "AUD", "CAD", "SGD", "THB", "IDR", "CNY", "KRW", "HKD", "MYR", "INR", "CHF", "PHP")


def _get(url, params):
    try:
        response = requests.get(url, params=params, timeout=(3, 10), headers={
            "User-Agent": "TripWise/1.0 (local student travel planner)",
            "Accept": "application/json",
        })
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError()
        return payload
    except (requests.RequestException, ValueError):
        # Never expose the upstream request URL: it may contain an API key.
        raise APIError("This service is temporarily unavailable. Please try again later.") from None


def _cached(key, seconds, load):
    value = cache.get(key)
    if value is None:
        value = load()
        cache.set(key, value, seconds)
    return value


def search_destinations(query):
    if not settings.GEOAPIFY_API_KEY:
        raise APIError("Destination search is not configured yet. Please contact the site administrator.")
    query = query.strip()
    if not 2 <= len(query) <= 200:
        raise APIError("Enter a destination between 2 and 200 characters.")
    def load():
        payload = _get("https://api.geoapify.com/v1/geocode/search", {
            "text": query, "format": "json", "limit": 5, "lang": "en",
            "apiKey": settings.GEOAPIFY_API_KEY,
        })
        try:
            results = []
            for row in payload["results"]:
                lat, lon = float(row["lat"]), float(row["lon"])
                if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                results.append({"label": str(row["formatted"])[:300], "lat": lat, "lon": lon})
            return results
        except (KeyError, TypeError, ValueError):
            raise APIError("Destination search returned an unexpected response.") from None
    return _cached("geo:" + hashlib.sha256(query.casefold().encode()).hexdigest(), 86400, load)


def weather(latitude, longitude, start, end):
    today = date.today()
    first, last = max(today, start), min(today + timedelta(days=15), end)
    if first > last:
        raise APIError("Forecasts cover only the next 16 days. Check back closer to your trip.")
    def load():
        data = _get("https://api.open-meteo.com/v1/forecast", {
            "latitude": latitude, "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "start_date": first.isoformat(), "end_date": last.isoformat(), "timezone": "auto",
        })
        try:
            daily = data["daily"]
            days = [{"date": day, "high": high, "low": low, "rain": rain} for day, high, low, rain in zip(
                daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"], daily["precipitation_probability_max"], strict=True)]
            if not days:
                raise ValueError()
            return {"days": days, "timezone": data.get("timezone", ""), "partial": first != start or last != end}
        except (KeyError, TypeError, ValueError):
            raise APIError("The weather service returned an unexpected response.") from None
    return _cached(f"weather:{latitude}:{longitude}:{first}:{last}", 1800, load)


def convert_budget(amount, target):
    target = target.upper()
    if target not in CURRENCIES:
        raise APIError("Choose one of the available currencies.")
    if target == "PHP":
        return {"amount": str(amount), "currency": "PHP", "rate": "1", "date": date.today().isoformat()}
    def load():
        data = _get(f"https://api.frankfurter.dev/v2/rate/php/{target.lower()}", {})
        try:
            rate = Decimal(str(data["rate"]))
            if not rate.is_finite() or rate <= 0 or str(data["base"]).upper() != "PHP" or str(data["quote"]).upper() != target:
                raise ValueError()
            return {"rate": str(rate), "date": str(data["date"])}
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise APIError("The exchange-rate service returned an unexpected response.") from None
    data = _cached(f"rate:PHP:{target}", 3600, load)
    return {**data, "currency": target, "amount": str((amount * Decimal(data["rate"])).quantize(Decimal("0.01")))}


def destination_info(query):
    def load():
        data = _get("https://en.wikipedia.org/w/api.php", {
            "action": "query", "generator": "search", "gsrsearch": query,
            "gsrnamespace": 0, "gsrlimit": 1, "prop": "extracts|info",
            "exintro": 1, "explaintext": 1, "exchars": 1400, "inprop": "url", "format": "json",
        })
        try:
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                raise APIError("No Wikipedia article was found for this destination.")
            row = next(iter(pages.values()))
            url = row["fullurl"]
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "en.wikipedia.org":
                raise ValueError()
            return {"title": row["title"], "extract": row.get("extract", "No introduction is available."), "url": url}
        except (KeyError, TypeError, ValueError):
            raise APIError("Wikipedia returned an unexpected response.") from None
    return _cached("wiki:" + hashlib.sha256(query.casefold().encode()).hexdigest(), 86400, load)


def _cloud_credentials():
    cloud = settings.CLOUDINARY_CLOUD_NAME
    if not all((cloud, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET)):
        raise APIError("Photo storage is not configured yet. Please contact the site administrator.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cloud):
        raise APIError("Photo storage configuration needs attention.")
    return cloud


class PhotoUploadError(APIError):
    def __init__(self, message, admin_message=None):
        super().__init__(message)
        self.admin_message = admin_message or message


def upload_photo(upload, trip_id):
    cloud = _cloud_credentials()
    public_id = f"tripwise/trip_{trip_id}/{uuid.uuid4().hex}"
    upload.seek(0)
    # Keep an extension matching the validated image rather than trusting its filename.
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(upload.content_type, "jpg")
    try:
        response = requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
            auth=(settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET),
            data={"public_id": public_id, "allowed_formats": "jpg,png,webp"},
            files={"file": (f"photo.{extension}", upload, upload.content_type)}, timeout=(5, 30))
        response.raise_for_status()
        data = response.json()
        url = data["secure_url"]
        if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "res.cloudinary.com" or data["public_id"] != public_id:
            raise ValueError()
        return {"url": url, "public_id": public_id}
    except requests.Timeout:
        raise PhotoUploadError("The upload took too long. Check your connection and try again.") from None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status in (401, 403):
            raise PhotoUploadError(
                "Photo storage could not verify the site's connection. Please ask the site owner to check photo storage settings.",
                "Cloudinary rejected the credentials. In api_credentials.json, use the cloud name, API key, and matching API secret from the same Cloudinary environment. Save the file and restart Django.",
            ) from None
        if status == 413:
            raise PhotoUploadError("This photo exceeds the storage service's upload limit. Choose a smaller image.") from None
        if status == 429:
            raise PhotoUploadError("Photo storage is receiving too many uploads. Please wait a moment and try again.") from None
        if status == 400:
            raise PhotoUploadError("Photo storage could not accept this image. Try a different JPEG, PNG, or WebP photo.",
                "Cloudinary rejected this upload. Check the cloud name and image format in your Cloudinary environment.") from None
        raise PhotoUploadError("Photo storage is temporarily unavailable. Please try again later.") from None
    except requests.RequestException:
        raise PhotoUploadError("Could not reach photo storage. Check your connection and try again.") from None
    except (ValueError, KeyError, TypeError):
        raise PhotoUploadError("Photo storage returned an unexpected response. Please try again later.") from None


def delete_cloud_photo(public_id):
    cloud = _cloud_credentials()
    timestamp = str(int(time.time()))
    signature = hashlib.sha1(f"public_id={public_id}&timestamp={timestamp}{settings.CLOUDINARY_API_SECRET}".encode()).hexdigest()
    try:
        response = requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/image/destroy", data={
            "public_id": public_id, "timestamp": timestamp, "signature": signature, "api_key": settings.CLOUDINARY_API_KEY,
        }, timeout=(5, 15))
        response.raise_for_status()
        if response.json().get("result") not in ("ok", "not found"):
            raise ValueError()
    except (requests.RequestException, ValueError, TypeError):
        raise APIError("Photo deletion failed. Please try again later.") from None
