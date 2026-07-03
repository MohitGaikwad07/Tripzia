from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0007_remove_booking_payment_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="trip",
            name="gallery_urls",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="inclusions",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="places_covered",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="pricing_details",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="review_rating",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="review_summary",
            field=models.TextField(blank=True),
        ),
    ]
