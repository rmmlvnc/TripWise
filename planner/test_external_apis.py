from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch, Mock
from PIL import Image
import requests
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from planner.models import Trip, TripPhoto
from planner.forms import PhotoForm
from planner import services


def image_file():
    stream = BytesIO()
    Image.new('RGB', (4, 4)).save(stream, 'PNG')
    return SimpleUploadedFile('test.png', stream.getvalue(), content_type='image/png')


@override_settings(GEOAPIFY_API_KEY='test-key', CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='test-api-key', CLOUDINARY_API_SECRET='test-secret')
@override_settings(WEATHER_PERSISTENT_CACHE=False)
class ServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('planner.services.requests.get')
    def test_geocoding_request_and_cache(self, get):
        get.return_value.json.return_value = {'results': [{'formatted': 'Tokyo, Japan', 'lat': 35.68, 'lon': 139.69}]}
        self.assertEqual(services.search_destinations('Tokyo')[0]['lat'], 35.68)
        services.search_destinations('Tokyo')
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs['params']['apiKey'], 'test-key')
        self.assertIn('timeout', get.call_args.kwargs)

    @patch('planner.services.requests.get')
    def test_geocoding_failure_hides_credentials(self, get):
        get.side_effect = requests.Timeout('URL contains test-key')
        with self.assertRaises(services.APIError) as error:
            services.search_destinations('Tokyo')
        self.assertNotIn('test-key', str(error.exception))

    @override_settings(GEOAPIFY_API_KEY='')
    @patch('planner.services.requests.get')
    def test_missing_key_does_not_call_provider(self, get):
        with self.assertRaisesMessage(services.APIError, 'not configured'):
            services.search_destinations('Tokyo')
        get.assert_not_called()

    @patch('planner.services.requests.get')
    def test_php_conversion_uses_reference_rate(self, get):
        get.return_value.json.return_value = {'base': 'PHP', 'quote': 'USD', 'rate': .017, 'date': '2026-11-09'}
        result = services.convert_budget(Decimal('1000'), 'USD')
        self.assertEqual(result['amount'], '17.00')
        self.assertEqual(result['date'], '2026-11-09')
        with self.assertRaises(services.APIError):
            services.convert_budget(Decimal('1000'), '../bad')

    @patch('planner.services.requests.get')
    def test_weather_uses_only_overlapping_trip_dates(self, get):
        today = date.today()
        get.return_value.json.return_value = {'timezone': 'Asia/Tokyo', 'daily': {'time': [today.isoformat()], 'temperature_2m_max': [22], 'temperature_2m_min': [15], 'precipitation_probability_max': [40]}}
        result = services.weather(35.68, 139.69, today - timedelta(days=1), today + timedelta(days=30))
        self.assertTrue(result['partial'])
        self.assertEqual(result['days'][0]['high'], 22)
        self.assertEqual(get.call_args.kwargs['params']['end_date'], (today + timedelta(days=15)).isoformat())

    @patch('planner.services.requests.get')
    def test_far_future_trip_does_not_request_fake_forecast(self, get):
        with self.assertRaisesMessage(services.APIError, '16 days'):
            services.weather(35, 139, date.today() + timedelta(days=30), date.today() + timedelta(days=40))
        get.assert_not_called()

    @patch('planner.services.requests.get')
    def test_wikipedia_extract_and_attribution_url(self, get):
        get.return_value.json.return_value = {'query': {'pages': {'1': {'title': 'Tokyo', 'extract': 'A city in Japan.', 'fullurl': 'https://en.wikipedia.org/wiki/Tokyo'}}}}
        result = services.destination_info('Tokyo')
        self.assertEqual(result['extract'], 'A city in Japan.')
        self.assertEqual(result['url'], 'https://en.wikipedia.org/wiki/Tokyo')

    @patch('planner.services.requests.get')
    def test_malformed_data_has_friendly_error(self, get):
        get.return_value.json.return_value = {'rate': 'NaN', 'base': 'PHP', 'quote': 'USD', 'date': 'bad'}
        with self.assertRaises(services.APIError):
            services.convert_budget(Decimal('10'), 'USD')

    @patch('planner.services.requests.post')
    def test_cloudinary_authenticated_upload(self, post):
        def response(*args, **kwargs):
            return Mock(json=lambda: {'secure_url': 'https://res.cloudinary.com/test-cloud/image/upload/sample.png', 'public_id': kwargs['data']['public_id']})
        post.side_effect = response
        result = services.upload_photo(image_file(), 4)
        self.assertTrue(result['public_id'].startswith('tripwise/trip_4/'))
        self.assertEqual(post.call_args.kwargs['auth'], ('test-api-key', 'test-secret'))

    @patch('planner.services.requests.post')
    def test_cloudinary_delete_failure_preserved(self, post):
        post.return_value.json.return_value = {'result': 'error'}
        with self.assertRaises(services.APIError):
            services.delete_cloud_photo('tripwise/photo')

    def test_photo_validation(self):
        self.assertTrue(PhotoForm({}, {'photo': image_file()}).is_valid())
        invalid = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
        self.assertFalse(PhotoForm({}, {'photo': invalid}).is_valid())


class APIViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('api-user', password='samplepassword')
        self.other = User.objects.create_user('other-user', password='samplepassword')
        self.trip = Trip.objects.create(owner=self.user, destination='Tokyo', start_date=date.today(), end_date=date.today(), budget=1000)
        self.client.force_login(self.user)

    def test_trip_page_contains_all_five_tools_without_network(self):
        with patch('planner.services.requests.get') as get:
            response = self.client.get(reverse('trip_detail', args=[self.trip.pk]))
        self.assertEqual(response.status_code, 200)
        for name in ['Geoapify', 'Open-Meteo', 'Frankfurter', 'Wikipedia', 'Cloudinary']:
            self.assertContains(response, name)
        get.assert_not_called()

    @patch('planner.services.search_destinations')
    def test_location_selection_is_signed_and_persisted(self, search):
        search.return_value = [{'label': 'Tokyo, Japan', 'lat': 35.68, 'lon': 139.69}]
        response = self.client.get(reverse('trip_api', args=[self.trip.pk, 'destinations']), {'q': 'Tokyo'})
        token = response.json()['results'][0]['token']
        self.client.post(reverse('select_destination', args=[self.trip.pk]), {'token': token})
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.latitude, 35.68)
        self.assertEqual(self.trip.location_label, 'Tokyo, Japan')

    def test_tampered_selection_is_not_saved(self):
        self.client.post(reverse('select_destination', args=[self.trip.pk]), {'token': 'tampered'})
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.latitude)

    def test_api_and_photos_are_owner_only(self):
        photo = TripPhoto.objects.create(trip=self.trip, public_id='tripwise/test', url='https://res.cloudinary.com/test/image.png')
        self.client.force_login(self.other)
        for provider in ['destinations', 'weather', 'currency', 'wikipedia']:
            self.assertEqual(self.client.get(reverse('trip_api', args=[self.trip.pk, provider])).status_code, 404)
        self.assertEqual(self.client.post(reverse('select_destination', args=[self.trip.pk]), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('photo_upload', args=[self.trip.pk]), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('photo_delete', args=[photo.pk]), {}).status_code, 404)

    @patch('planner.services.upload_photo')
    def test_uploaded_photo_url_is_saved(self, upload):
        upload.return_value = {'url': 'https://res.cloudinary.com/test/image/upload/test.png', 'public_id': 'tripwise/test'}
        response = self.client.post(reverse('photo_upload', args=[self.trip.pk]), {'photo': image_file(), 'caption': 'A memory'})
        self.assertRedirects(response, reverse('trip_detail', args=[self.trip.pk]) + '#trip-photos')
        self.assertEqual(TripPhoto.objects.get().caption, 'A memory')

    @patch('planner.services.delete_cloud_photo')
    def test_failed_remote_delete_keeps_photo_record(self, delete):
        photo = TripPhoto.objects.create(trip=self.trip, public_id='tripwise/test', url='https://res.cloudinary.com/test/image.png')
        delete.side_effect = services.APIError('Service unavailable')
        self.client.post(reverse('photo_delete', args=[photo.pk]))
        self.assertTrue(TripPhoto.objects.filter(pk=photo.pk).exists())

    def test_changing_destination_clears_old_coordinates(self):
        self.trip.latitude = 35.68
        self.trip.longitude = 139.69
        self.trip.location_label = 'Tokyo, Japan'
        self.trip.save()
        self.client.post(reverse('trip_edit', args=[self.trip.pk]), {'destination': 'Kyoto', 'start_date': date.today().isoformat(), 'end_date': date.today().isoformat(), 'budget': '1000', 'notes': ''})
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.latitude)
        self.assertEqual(self.trip.location_label, '')

    @patch('planner.services.convert_budget')
    def test_external_error_returns_json_without_crashing_trip(self, convert):
        convert.side_effect = services.APIError('Try again later.')
        response = self.client.get(reverse('trip_api', args=[self.trip.pk, 'currency']))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'Try again later.')

    @patch('planner.services.upload_photo')
    def test_ajax_upload_failure_is_retryable_and_hides_admin_details(self, upload):
        upload.side_effect = services.PhotoUploadError('Photo storage authentication failed.', 'Check the matching Cloudinary secret.')
        response = self.client.post(reverse('photo_upload', args=[self.trip.pk]), {'photo': image_file(), 'caption': 'Keep this caption'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error'], 'Photo storage authentication failed.')
        self.assertEqual(TripPhoto.objects.count(), 0)
        self.user.is_staff = True
        self.user.save()
        response = self.client.post(reverse('photo_upload', args=[self.trip.pk]), {'photo': image_file()}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json()['error'], 'Check the matching Cloudinary secret.')

    @patch('planner.services.upload_photo')
    def test_ajax_upload_success_persists_photo(self, upload):
        upload.return_value = {'url': 'https://res.cloudinary.com/test/image/upload/test.png', 'public_id': 'tripwise/ajax'}
        response = self.client.post(reverse('photo_upload', args=[self.trip.pk]), {'photo': image_file(), 'caption': 'Saved'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(TripPhoto.objects.get().caption, 'Saved')

    def test_ajax_invalid_image_returns_validation_error(self):
        response = self.client.post(reverse('photo_upload', args=[self.trip.pk]), {'photo': SimpleUploadedFile('fake.png', b'bad data')}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Photo:', response.json()['error'])
        self.assertEqual(TripPhoto.objects.count(), 0)


@override_settings(CLOUDINARY_CLOUD_NAME='test-cloud', CLOUDINARY_API_KEY='secret-key', CLOUDINARY_API_SECRET='secret-value')
class PhotoProviderFailureTests(SimpleTestCase):
    @patch('planner.services.requests.post')
    def test_authentication_failure_has_safe_error(self, post):
        response = Mock(status_code=401)
        post.return_value.raise_for_status.side_effect = requests.HTTPError('secret-value must never be exposed', response=response)
        with self.assertRaises(services.PhotoUploadError) as failure:
            services.upload_photo(image_file(), 1)
        self.assertIn('connection', str(failure.exception))
        self.assertNotIn('secret-value', str(failure.exception))
        self.assertNotIn('secret-key', failure.exception.admin_message)

    @patch('planner.services.requests.post')
    def test_upload_timeout_has_retry_message(self, post):
        post.side_effect = requests.Timeout('request included secret-value')
        with self.assertRaisesMessage(services.PhotoUploadError, 'took too long'):
            services.upload_photo(image_file(), 1)


@override_settings(WEATHER_PERSISTENT_CACHE=False)
class WeatherRecoveryTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('planner.services.time.sleep')
    @patch('planner.services.requests.get')
    def test_weather_recovers_after_one_timeout(self, get, sleep):
        get.side_effect = [requests.Timeout('private request data'), Mock(json=lambda: {'daily': {'time': [date.today().isoformat()], 'temperature_2m_max': [30], 'temperature_2m_min': [24], 'precipitation_probability_max': [20]}, 'timezone': 'Asia/Manila'})]
        result = services.weather(9.80742, 126.15996, date.today(), date.today())
        self.assertEqual(get.call_count, 2)
        self.assertEqual(result['days'][0]['high'], 30)
        self.assertEqual(get.call_args.kwargs['timeout'], (3, 6))

    @patch('planner.services.requests.get')
    def test_rate_limit_is_not_retried(self, get):
        response = Mock(status_code=429)
        get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        with self.assertRaisesMessage(services.APIError, 'request limit'):
            services.weather(9, 126, date.today(), date.today())
        self.assertEqual(get.call_count, 1)

    @patch('planner.services.time.sleep')
    @patch('planner.services.requests.get')
    def test_server_error_retries_once_and_logs_only_status(self, get, sleep):
        response = Mock(status_code=503)
        get.return_value.raise_for_status.side_effect = requests.HTTPError('private URL and headers', response=response)
        with self.assertLogs('planner.services', level='WARNING') as logs:
            with self.assertRaisesMessage(services.APIError, 'temporarily unavailable'):
                services.weather(9, 126, date.today(), date.today())
        self.assertEqual(get.call_count, 2)
        self.assertIn('status=503', ' '.join(logs.output))
        self.assertNotIn('private URL', ' '.join(logs.output))

    @patch('planner.services.requests.get')
    def test_invalid_coordinates_and_past_trip_do_not_call_provider(self, get):
        with self.assertRaisesMessage(services.APIError, 'destination again'):
            services.weather(float('nan'), 126, date.today(), date.today())
        with self.assertRaisesMessage(services.APIError, 'trip has ended'):
            services.weather(9, 126, date.today()-timedelta(days=3), date.today()-timedelta(days=1))
        get.assert_not_called()

    @patch('planner.services.requests.get')
    def test_bad_request_has_date_guidance_without_retry(self, get):
        response = Mock(status_code=400)
        get.return_value.raise_for_status.side_effect = requests.HTTPError(response=response)
        with self.assertRaisesMessage(services.APIError, 'travel dates'):
            services.weather(9, 126, date.today(), date.today())
        self.assertEqual(get.call_count, 1)
