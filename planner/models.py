from datetime import date
from django.conf import settings
from django.db import models


class Trip(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trips",
    )
    destination = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    notes = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_label = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.destination

class Expense(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="expenses")
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=date.today)

    def __str__(self):
        return self.title


class TripPhoto(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="photos")
    url = models.URLField(max_length=1000)
    public_id = models.CharField(max_length=300, unique=True)
    caption = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ForecastCache(models.Model):
    """Shared public forecasts and the provider-wide request cooldown."""
    key = models.CharField(max_length=200, unique=True)
    payload = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(null=True, blank=True)
    retry_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
