from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0003_trip_image_file"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Booking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("traveler_name", models.CharField(max_length=200)),
                ("traveler_email", models.EmailField(max_length=254)),
                ("traveler_phone", models.CharField(blank=True, max_length=30)),
                ("travelers_count", models.PositiveIntegerField(default=1)),
                ("special_request", models.TextField(blank=True)),
                ("booked_at", models.DateTimeField(auto_now_add=True)),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bookings", to="planner.trip")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trip_bookings", to="auth.user")),
            ],
            options={
                "ordering": ["-booked_at"],
            },
        ),
    ]
