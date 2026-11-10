from datetime import date, timedelta
from unittest.mock import Mock, patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse
from planner.models import ForecastCache, Trip
from planner import services


def payload():
    return {"location": {"tz_id": "Asia/Manila"}, "forecast": {"forecastday": [{"date": date.today().isoformat(), "day": {"maxtemp_c": 30, "mintemp_c": 24, "daily_chance_of_rain": 20}}]}}


@override_settings(WEATHERAPI_API_KEY="test-weather-key")
class PersistentWeatherTests(TestCase):
    def check(self, lat=9.80742):
        return services.weather(lat, 126.15996, date.today(), date.today())

    @patch("planner.services._get")
    def test_forecast_persists_and_is_reused_without_upstream_request(self, get):
        get.return_value = payload()
        first = self.check()
        second = self.check()
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(get.call_count, 1)
        self.assertEqual(ForecastCache.objects.exclude(key="weatherapi:control").count(), 1)

    @patch("planner.services._get")
    def test_old_open_meteo_cooldown_does_not_block_weatherapi(self, get):
        ForecastCache.objects.create(key="open-meteo:control", retry_at=timezone.now()+timedelta(hours=6))
        get.return_value=payload()
        self.assertFalse(self.check()["stale"])
        get.assert_called_once()

    @patch("planner.services._get")
    def test_rate_limit_pauses_all_destinations(self, get):
        get.side_effect = services.WeatherRateLimit("Provider request limit", 7200)
        with self.assertRaises(services.WeatherRateLimit):
            self.check()
        with self.assertRaises(services.WeatherRateLimit) as result:
            self.check(lat=10)
        self.assertGreater(result.exception.retry_after, 7100)
        self.assertEqual(get.call_count, 1)

    @patch("planner.services._get")
    def test_saved_forecast_is_dated_when_provider_is_unavailable(self, get):
        get.return_value = payload()
        self.check()
        ForecastCache.objects.exclude(key="weatherapi:control").update(fetched_at=timezone.now()-timedelta(hours=1))
        ForecastCache.objects.filter(key="weatherapi:control").update(locked_until=None)
        get.side_effect = services.WeatherRateLimit("Provider request limit", 900)
        result = self.check()
        self.assertTrue(result["stale"])
        self.assertEqual(result["days"][0]["high"], 30)
        self.assertIn("updated_at", result)
        self.assertEqual(result["retry_after"], 900)

    @patch("planner.services._get")
    def test_expired_saved_forecast_is_not_presented_as_current(self, get):
        get.return_value = payload()
        self.check()
        ForecastCache.objects.exclude(key="weatherapi:control").update(fetched_at=timezone.now()-timedelta(hours=7))
        ForecastCache.objects.filter(key="weatherapi:control").update(retry_at=timezone.now()+timedelta(minutes=5))
        with self.assertRaises(services.WeatherRateLimit):
            self.check()
        self.assertEqual(get.call_count, 1)

    @patch("planner.services._get")
    def test_worker_lock_prevents_duplicate_fetches(self, get):
        ForecastCache.objects.create(key="weatherapi:control", locked_until=timezone.now()+timedelta(seconds=25))
        with self.assertRaisesMessage(services.WeatherRateLimit, "Another forecast"):
            self.check()
        get.assert_not_called()

    @patch("planner.services._get")
    def test_expired_cooldown_allows_new_forecast(self, get):
        ForecastCache.objects.create(key="weatherapi:control", retry_at=timezone.now()-timedelta(seconds=1), locked_until=None)
        get.return_value = payload()
        self.assertFalse(self.check()["stale"])
        self.assertIsNone(ForecastCache.objects.get(key="weatherapi:control").retry_at)

    @patch("planner.services.weather")
    def test_api_sends_retry_after_and_rate_limit_status(self, weather):
        user=User.objects.create_user("cache-user",password="samplepassword")
        trip=Trip.objects.create(owner=user,destination="Siargao",start_date=date.today(),end_date=date.today(),budget=100,latitude=9,longitude=126)
        self.client.force_login(user)
        weather.side_effect=services.WeatherRateLimit("Wait before retrying",3600)
        result=self.client.get(reverse("trip_api",args=[trip.pk,"weather"]))
        self.assertEqual(result.status_code,429)
        self.assertEqual(result["Retry-After"],"3600")
        self.assertEqual(result.json()["retry_after"],3600)


class RetryHeaderTests(SimpleTestCase):
    def test_retry_after_seconds_and_http_date(self):
        self.assertEqual(services._retry_seconds(Mock(headers={"Retry-After":"3600"})),3600)
        self.assertEqual(services._retry_seconds(Mock(headers={})),900)
        future=timezone.now()+timedelta(hours=2)
        value=future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertGreater(services._retry_seconds(Mock(headers={"Retry-After":value})),7100)
