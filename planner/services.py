"""Server-side external APIs. No credentials are sent to the browser."""

import hashlib
import logging
import math
import re
import time
import uuid
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone


logger = logging.getLogger(__name__)


class APIError(Exception):
    pass


class WeatherRateLimit(APIError):
    def __init__(self, message, retry_after=900):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


def _retry_seconds(response):
    value = response.headers.get("Retry-After", "")
    if isinstance(value, str):
        try:
            return max(1, min(int(value), 7 * 86400))
        except ValueError:
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.get_current_timezone())
                return max(1, min(int((stamp - timezone.now()).total_seconds()), 7 * 86400))
            except (ValueError, TypeError, OverflowError):
                pass
    # The actual quota window is unknown without a provider Retry-After header.
    return 900


CURRENCIES = (
    "USD", "EUR", "JPY", "GBP", "AUD", "CAD", "SGD", "THB",
    "IDR", "CNY", "KRW", "HKD", "MYR", "INR", "CHF", "PHP",
)


def _get(url, params):
    host = urlsplit(url).hostname
    is_weather = host == "api.open-meteo.com"
    # Retry only safe weather GETs; keep the total below Gunicorn's default timeout.
    attempts = 2 if is_weather else 1
    for attempt in range(attempts):
        response = None
        try:
            response = requests.get(url, params=params, timeout=(3, 6) if is_weather else (3, 10), headers={
                "User-Agent": "TripWise/1.0 (local student travel planner)",
                "Accept": "application/json",
            })
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError()
            if is_weather and payload.get("error"):
                logger.warning("Open-Meteo returned error=true")
                raise APIError("The weather provider could not process these trip dates. Check your destination and dates, then try again.")
            return payload
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if is_weather:
                # Never log URLs, request params, headers, or raw exception text.
                logger.warning("Open-Meteo HTTP status=%s attempt=%s", status, attempt + 1)
                if status >= 500 and attempt + 1 < attempts:
                    time.sleep(0.25)
                    continue
                if status == 429:
                    raise WeatherRateLimit("The weather provider has reached its request limit. New checks are paused to avoid repeated requests. The provider may need longer to reset.", _retry_seconds(exc.response)) from None
                if status == 400:
                    raise APIError("The weather provider could not process these trip dates. Check the selected destination and travel dates.") from None
                if status in (401, 403):
                    raise APIError("The weather provider is refusing requests from this server. Please contact the site owner.") from None
                raise APIError("The weather provider is temporarily unavailable. Please try again shortly.") from None
            logger.warning("External API failed: host=%s status=%s", host, response.status_code if response is not None else "none")
            raise APIError("This service is temporarily unavailable. Please try again later.") from None
        except (requests.Timeout, requests.ConnectionError) as exc:
            if is_weather:
                logger.warning("Open-Meteo connection failure=%s attempt=%s", type(exc).__name__, attempt + 1)
                if attempt + 1 < attempts:
                    time.sleep(0.25)
                    continue
                raise APIError("The weather provider did not respond in time. Please check the forecast again shortly.") from None
            logger.warning("External API failed: host=%s status=%s", host, response.status_code if response is not None else "none")
            raise APIError("This service is temporarily unavailable. Please try again later.") from None
        except (requests.RequestException, ValueError):
            if is_weather:
                logger.warning("Open-Meteo response could not be read")
                raise APIError("The weather provider returned an unreadable response. Please try again shortly.") from None
            logger.warning("External API failed: host=%s status=%s", host, response.status_code if response is not None else "none")
            raise APIError("This service is temporarily unavailable. Please try again later.") from None


def _cached(key, seconds, load):
    value = cache.get(key)
    if value is None:
        value = load()
        cache.set(key, value, seconds)
    return value


def search_destinations(query):
    if not settings.GEOAPIFY_API_KEY:
        raise APIError(
            "Destination search is not configured yet. "
            "Please contact the site administrator."
        )

    query = query.strip()
    if not 2 <= len(query) <= 200:
        raise APIError("Enter a destination between 2 and 200 characters.")

    def load():
        payload = _get(
            "https://api.geoapify.com/v1/geocode/search",
            {
                "text": query,
                "format": "json",
                "limit": 5,
                "lang": "en",
                "apiKey": settings.GEOAPIFY_API_KEY,
            },
        )
        try:
            results = []
            for row in payload["results"]:
                lat = float(row["lat"])
                lon = float(row["lon"])
                if (
                    not math.isfinite(lat)
                    or not math.isfinite(lon)
                    or not (-90 <= lat <= 90 and -180 <= lon <= 180)
                ):
                    continue
                results.append({
                    "label": str(row["formatted"])[:300],
                    "lat": lat,
                    "lon": lon,
                })
            return results
        except (KeyError, TypeError, ValueError):
            raise APIError(
                "Destination search returned an unexpected response."
            ) from None

    key = "geo:" + hashlib.sha256(query.casefold().encode()).hexdigest()
    return _cached(key, 86400, load)


def weather(latitude, longitude, start, end):
    try:
        latitude, longitude = float(latitude), float(longitude)
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (TypeError, ValueError):
        raise APIError("Choose your destination again before checking its weather.") from None
    today = date.today()
    if end < today:
        raise APIError("This trip has ended. Upcoming weather is available only for current and future trip dates.")
    first, last = max(today, start), min(today + timedelta(days=15), end)
    if first > last:
        raise APIError(
            "Forecasts cover only the next 16 days. "
            "Check back closer to your trip."
        )

    def load():
        data = _get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": (
                    "temperature_2m_max,"
                    "temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "start_date": first.isoformat(),
                "end_date": last.isoformat(),
                "timezone": "auto",
            },
        )
        try:
            daily = data["daily"]
            days = [
                {
                    "date": day,
                    "high": high,
                    "low": low,
                    "rain": rain,
                }
                for day, high, low, rain in zip(
                    daily["time"],
                    daily["temperature_2m_max"],
                    daily["temperature_2m_min"],
                    daily["precipitation_probability_max"],
                    strict=True,
                )
            ]
            if not days:
                raise ValueError()
            return {
                "days": days,
                "timezone": data.get("timezone", ""),
                "partial": first != start or last != end,
            }
        except (KeyError, TypeError, ValueError):
            raise APIError(
                "The weather service returned an unexpected response."
            ) from None

    key = f"weather:{latitude}:{longitude}:{first}:{last}"
    if not getattr(settings, "WEATHER_PERSISTENT_CACHE", True):
        return _cached(key, 1800, load)
    return _persistent_forecast(key, load)


def _persistent_forecast(key, load):
    from .models import ForecastCache
    now = timezone.now()
    entry, _ = ForecastCache.objects.get_or_create(key=key)

    def saved(stale=False, wait=0):
        return {**entry.payload, "cached": True, "stale": stale,
                "updated_at": entry.fetched_at.isoformat(), "retry_after": wait}

    if entry.payload and entry.fetched_at and entry.fetched_at >= now - timedelta(minutes=30):
        return saved()

    control, _ = ForecastCache.objects.get_or_create(key="open-meteo:control")

    def fallback(error):
        if entry.payload and entry.fetched_at and entry.fetched_at >= now - timedelta(hours=6):
            return saved(stale=True, wait=getattr(error, "retry_after", 60))
        raise error

    if control.retry_at and control.retry_at > now:
        wait = max(1, int((control.retry_at - now).total_seconds()))
        return fallback(WeatherRateLimit("Weather checks are paused after a provider error or request limit. Please wait before trying again; the provider's reset time may be longer.", wait))

    # Atomic conditional update: only one worker may fetch across all destinations.
    acquired = ForecastCache.objects.filter(pk=control.pk).filter(
        Q(locked_until__isnull=True) | Q(locked_until__lte=now)
    ).update(locked_until=now + timedelta(seconds=30))
    if not acquired:
        return fallback(WeatherRateLimit("Another forecast is being checked. Please try again in a few seconds.", 5))
    try:
        control.refresh_from_db()
        if control.retry_at and control.retry_at > timezone.now():
            wait = max(1, int((control.retry_at - timezone.now()).total_seconds()))
            return fallback(WeatherRateLimit("Weather checks are paused while the provider recovers. Please try again later.", wait))
        # A different worker may have completed this same entry since our first read.
        entry.refresh_from_db()
        if entry.payload and entry.fetched_at and entry.fetched_at >= now - timedelta(minutes=30):
            return saved()
        payload = load()
        entry.payload = payload
        entry.fetched_at = timezone.now()
        entry.save(update_fields=["payload", "fetched_at"])
        ForecastCache.objects.filter(pk=control.pk).update(retry_at=None)
        return {**payload, "cached": False, "stale": False, "updated_at": entry.fetched_at.isoformat()}
    except APIError as exc:
        wait = getattr(exc, "retry_after", 60)
        ForecastCache.objects.filter(pk=control.pk).update(retry_at=timezone.now() + timedelta(seconds=wait))
        return fallback(exc)
    finally:
        # A small interval also prevents bursts of different uncached destinations.
        ForecastCache.objects.filter(pk=control.pk).update(locked_until=timezone.now() + timedelta(seconds=2))


def convert_budget(amount, target):
    target = target.upper()
    if target not in CURRENCIES:
        raise APIError("Choose one of the available currencies.")

    if target == "PHP":
        return {
            "amount": str(amount),
            "currency": "PHP",
            "rate": "1",
            "date": date.today().isoformat(),
        }

    def load():
        data = _get(
            f"https://api.frankfurter.dev/v2/rate/php/{target.lower()}",
            {},
        )
        try:
            rate = Decimal(str(data["rate"]))
            if (
                not rate.is_finite()
                or rate <= 0
                or str(data["base"]).upper() != "PHP"
                or str(data["quote"]).upper() != target
            ):
                raise ValueError()
            return {
                "rate": str(rate),
                "date": str(data["date"]),
            }
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise APIError(
                "The exchange-rate service returned an unexpected response."
            ) from None

    data = _cached(f"rate:PHP:{target}", 3600, load)
    converted = (amount * Decimal(data["rate"])).quantize(Decimal("0.01"))
    return {
        **data,
        "currency": target,
        "amount": str(converted),
    }


def destination_info(query):
    def load():
        data = _get(
            "https://en.wikipedia.org/w/api.php",
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 0,
                "gsrlimit": 1,
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 1400,
                "inprop": "url",
                "format": "json",
            },
        )
        try:
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                raise APIError(
                    "No Wikipedia article was found for this destination."
                )

            row = next(iter(pages.values()))
            url = row["fullurl"]
            if (
                urlsplit(url).scheme != "https"
                or urlsplit(url).hostname != "en.wikipedia.org"
            ):
                raise ValueError()

            return {
                "title": row["title"],
                "extract": row.get(
                    "extract", "No introduction is available."
                ),
                "url": url,
            }
        except (KeyError, TypeError, ValueError):
            raise APIError(
                "Wikipedia returned an unexpected response."
            ) from None

    key = "wiki:" + hashlib.sha256(query.casefold().encode()).hexdigest()
    return _cached(key, 86400, load)


def _cloud_credentials():
    cloud = settings.CLOUDINARY_CLOUD_NAME
    if not all((
        cloud,
        settings.CLOUDINARY_API_KEY,
        settings.CLOUDINARY_API_SECRET,
    )):
        raise APIError(
            "Photo storage is not configured yet. "
            "Please contact the site administrator."
        )

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

    # Use an extension matching the validated image.
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(upload.content_type, "jpg")

    try:
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
            auth=(
                settings.CLOUDINARY_API_KEY,
                settings.CLOUDINARY_API_SECRET,
            ),
            data={
                "public_id": public_id,
                "allowed_formats": "jpg,png,webp",
            },
            files={
                "file": (
                    f"photo.{extension}",
                    upload,
                    upload.content_type,
                ),
            },
            timeout=(5, 30),
        )
        response.raise_for_status()
        data = response.json()
        url = data["secure_url"]

        if (
            urlsplit(url).scheme != "https"
            or urlsplit(url).hostname != "res.cloudinary.com"
            or data["public_id"] != public_id
        ):
            raise ValueError()

        return {
            "url": url,
            "public_id": public_id,
        }

    except requests.Timeout:
        raise PhotoUploadError(
            "The upload took too long. "
            "Check your connection and try again."
        ) from None

    except requests.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else 0
        )

        if status in (401, 403):
            raise PhotoUploadError(
                "Photo storage could not verify the site's connection. "
                "Please ask the site owner to check photo storage settings.",
                "Cloudinary rejected the credentials. In api_credentials.json, "
                "use the cloud name, API key, and matching API secret from the "
                "same Cloudinary environment. Save the file and restart Django.",
            ) from None

        if status == 413:
            raise PhotoUploadError(
                "This photo exceeds the storage service's upload limit. "
                "Choose a smaller image."
            ) from None

        if status == 429:
            raise PhotoUploadError(
                "Photo storage is receiving too many uploads. "
                "Please wait a moment and try again."
            ) from None

        if status == 400:
            raise PhotoUploadError(
                "Photo storage could not accept this image. "
                "Try a different JPEG, PNG, or WebP photo.",
                "Cloudinary rejected this upload. Check the cloud name "
                "and image format in your Cloudinary environment.",
            ) from None

        raise PhotoUploadError(
            "Photo storage is temporarily unavailable. "
            "Please try again later."
        ) from None

    except requests.RequestException:
        raise PhotoUploadError(
            "Could not reach photo storage. "
            "Check your connection and try again."
        ) from None

    except (ValueError, KeyError, TypeError):
        raise PhotoUploadError(
            "Photo storage returned an unexpected response. "
            "Please try again later."
        ) from None


def delete_cloud_photo(public_id):
    cloud = _cloud_credentials()
    timestamp = str(int(time.time()))
    signature = hashlib.sha1(
        (
            f"public_id={public_id}&timestamp={timestamp}"
            f"{settings.CLOUDINARY_API_SECRET}"
        ).encode()
    ).hexdigest()

    try:
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/image/destroy",
            data={
                "public_id": public_id,
                "timestamp": timestamp,
                "signature": signature,
                "api_key": settings.CLOUDINARY_API_KEY,
            },
            timeout=(5, 15),
        )
        response.raise_for_status()

        if response.json().get("result") not in ("ok", "not found"):
            raise ValueError()

    except (requests.RequestException, ValueError, TypeError):
        raise APIError(
            "Photo deletion failed. Please try again later."
        ) from None
