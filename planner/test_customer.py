from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from planner.models import Trip, Expense


class CustomerFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('traveler', 'traveler@example.com', 'SampleSecurePass!741')
        self.other = User.objects.create_user('other', 'other@example.com', 'SampleSecurePass!741')
        self.trip = Trip.objects.create(owner=self.user, destination='Baguio', start_date=date(2027, 1, 1), end_date=date(2027, 1, 3), budget=5000)

    def test_public_pages_and_protected_dashboard(self):
        for name in ['login', 'register']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertRedirects(self.client.get(reverse('dashboard')), '/login/?next=/my-trips/')

    def test_register_logs_in_without_admin_privileges(self):
        response = self.client.post(reverse('register'), {'username': 'newtraveler', 'email': 'new@example.com', 'first_name': 'Sam', 'last_name': 'Rivera', 'password1': 'DifferentSecure!741', 'password2': 'DifferentSecure!741', 'is_staff': 'true'})
        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(username='newtraveler')
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Sam')
        self.assertEqual(user.last_name, 'Rivera')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, 'DifferentSecure!741')

    def test_login_logout_and_invalid_login(self):
        response = self.client.post(reverse('login'), {'username': 'traveler', 'password': 'incorrect'})
        self.assertContains(response, 'Please enter a correct username and password')
        response = self.client.post(reverse('login'), {'username': 'traveler', 'password': 'SampleSecurePass!741'})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))

    def test_trip_crud_and_expense_totals(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('trip_create'), {'destination': 'Cebu', 'start_date': '2027-02-01', 'end_date': '2027-02-03', 'budget': '8000', 'notes': 'Explore'})
        new = Trip.objects.get(destination='Cebu')
        self.assertRedirects(response, reverse('trip_detail', args=[new.pk]))
        self.assertEqual(new.owner, self.user)
        response = self.client.post(reverse('trip_detail', args=[new.pk]), {'title': 'Lunch', 'amount': '250', 'date': '2027-02-01'})
        self.assertRedirects(response, reverse('trip_detail', args=[new.pk]))
        self.assertContains(self.client.get(reverse('trip_detail', args=[new.pk])), '7,750', count=0)
        response = self.client.get(reverse('trip_detail', args=[new.pk]))
        self.assertEqual(response.context['remaining'], 7750)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total_spent'], 250)
        self.client.post(reverse('trip_edit', args=[new.pk]), {'destination': 'Cebu City', 'start_date': '2027-02-01', 'end_date': '2027-02-03', 'budget': '9000', 'notes': ''})
        new.refresh_from_db()
        self.assertEqual(new.destination, 'Cebu City')
        self.assertEqual(self.client.get(reverse('trip_delete', args=[new.pk])).status_code, 200)
        self.assertTrue(Trip.objects.filter(pk=new.pk).exists())
        self.client.post(reverse('trip_delete', args=[new.pk]))
        self.assertFalse(Expense.objects.filter(trip_id=new.pk).exists())
        self.assertFalse(Trip.objects.filter(pk=new.pk).exists())

    def test_ownership_checks(self):
        expense = Expense.objects.create(trip=self.trip, title='Private expense', amount=10)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'Baguio')
        for name in ['trip_detail', 'trip_edit', 'trip_delete']:
            url = reverse(name, args=[self.trip.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('expense_delete', args=[expense.pk])).status_code, 404)

    def test_invalid_dates_and_amounts(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('trip_create'), {'destination': 'Invalid', 'start_date': '2027-02-03', 'end_date': '2027-02-01', 'budget': '-10'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('end_date', response.context['form'].errors)
        self.assertIn('budget', response.context['form'].errors)
        response = self.client.post(reverse('trip_detail', args=[self.trip.pk]), {'title': 'Invalid', 'amount': '-2', 'date': '2027-01-01'})
        self.assertIn('amount', response.context['form'].errors)
        self.assertEqual(Expense.objects.count(), 0)

    def test_csrf_is_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('register'), {}).status_code, 403)

    def test_duplicate_email_and_unsafe_redirect(self):
        response = self.client.post(reverse('register'), {'username': 'different', 'first_name': 'Other', 'last_name': 'Traveler', 'email': 'TRAVELER@example.com', 'password1': 'DifferentSecure!741', 'password2': 'DifferentSecure!741'})
        self.assertIn('email', response.context['form'].errors)
        response = self.client.post(reverse('login'), {'username': 'traveler', 'password': 'SampleSecurePass!741', 'next': 'https://example.com'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_last_name_is_required_and_rendered(self):
        response = self.client.get(reverse('register'))
        self.assertContains(response, 'name="last_name"')
        response = self.client.post(reverse('register'), {
            'username': 'missingname', 'first_name': 'Sam', 'last_name': '   ',
            'email': 'missing@example.com', 'password1': 'DifferentSecure!741',
            'password2': 'DifferentSecure!741',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('last_name', response.context['form'].errors)
        self.assertFalse(User.objects.filter(username='missingname').exists())
