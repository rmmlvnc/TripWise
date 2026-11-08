from datetime import date, timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from planner.models import Trip


class UsabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("guide-user", password="StrongSample!741")
        self.other = User.objects.create_user("private-user", password="StrongSample!741")
        self.client.force_login(self.user)
        self.today = date.today()
        self.upcoming = Trip.objects.create(owner=self.user, destination="Tokyo", start_date=self.today + timedelta(days=2), end_date=self.today + timedelta(days=5), budget=5000)
        self.past = Trip.objects.create(owner=self.user, destination="Kyoto", start_date=self.today - timedelta(days=5), end_date=self.today - timedelta(days=2), budget=3000)
        Trip.objects.create(owner=self.other, destination="Private Tokyo", start_date=self.today, end_date=self.today, budget=9000)

    def test_search_is_scoped_to_owner_and_totals_stay_global(self):
        response = self.client.get(reverse("dashboard"), {"q": "Tokyo"})
        self.assertEqual(response.context["filtered_count"], 1)
        self.assertEqual(response.context["total_budget"], 8000)
        self.assertEqual([t.pk for t in response.context["trips"]], [self.upcoming.pk])
        self.assertNotContains(response, "Private Tokyo")

    def test_trip_status_filters_and_empty_result(self):
        response = self.client.get(reverse("dashboard"), {"status": "past"})
        self.assertEqual([t.pk for t in response.context["trips"]], [self.past.pk])
        response = self.client.get(reverse("dashboard"), {"q": "No such city"})
        self.assertContains(response, "No trips match your search.")
        self.assertNotContains(response, "Plan my first trip")
        response = self.client.get(reverse("dashboard"), {"status": "unexpected"})
        self.assertEqual(response.context["status"], "all")

    def test_pagination_preserves_search(self):
        for number in range(10):
            Trip.objects.create(owner=self.user, destination=f"Tokyo {number}", start_date=self.today, end_date=self.today, budget=1)
        response = self.client.get(reverse("dashboard"), {"q": "Tokyo", "page": 1})
        self.assertEqual(len(response.context["trips"]), 9)
        self.assertContains(response, "q=Tokyo&amp;status=all&amp;page=2")
        response = self.client.get(reverse("dashboard"), {"q": "Tokyo", "page": 2})
        self.assertEqual(len(response.context["trips"]), 2)

    def test_help_and_destination_guidance(self):
        self.assertContains(self.client.get(reverse("help")), "How to use TripWise")
        response = self.client.get(reverse("trip_detail", args=[self.upcoming.pk]))
        self.assertContains(response, "Choose a location first")
        self.assertContains(response, "Next: confirm your destination")
        self.upcoming.latitude, self.upcoming.longitude = 35.68, 139.69
        self.upcoming.location_label = "Tokyo, Japan"
        self.upcoming.save()
        response = self.client.get(reverse("trip_detail", args=[self.upcoming.pk]))
        self.assertContains(response, "Check forecast")
        self.assertNotContains(response, "Next: confirm your destination")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("help")).status_code, 302)
