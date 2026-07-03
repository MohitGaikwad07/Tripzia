from django.db import models
from django.contrib.auth.models import User


class Trip(models.Model):
    title = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    places_covered = models.TextField(blank=True)
    pricing_details = models.TextField(blank=True)
    review_summary = models.TextField(blank=True)
    review_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    gallery_urls = models.TextField(blank=True)
    inclusions = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    image_file = models.FileField(upload_to="trip_images/", blank=True)
    duration_days = models.PositiveIntegerField(default=3)
    price_label = models.CharField(max_length=100, blank=True)
    trip_style = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.destination}"


class Booking(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trip_bookings")
    traveler_name = models.CharField(max_length=200)
    traveler_email = models.EmailField()
    traveler_phone = models.CharField(max_length=30, blank=True)
    travelers_count = models.PositiveIntegerField(default=1)
    special_request = models.TextField(blank=True)
    booked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-booked_at"]

    def __str__(self):
        return f"{self.traveler_name} - {self.trip.title}"


class RouteHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="route_histories")
    route_title = models.CharField(max_length=255)
    destination = models.CharField(max_length=200)
    total_estimated_cost = models.CharField(max_length=100, blank=True)
    days = models.PositiveIntegerField(default=1)
    budget = models.CharField(max_length=50, blank=True)
    trip_snapshot = models.JSONField(default=dict, blank=True)
    admin_notes = models.TextField(blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at"]

    def __str__(self):
        return f"{self.user.username} - {self.destination} - {self.route_title}"
