from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0002_trip_library_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="trip",
            name="image_file",
            field=models.FileField(blank=True, upload_to="trip_images/"),
        ),
    ]
