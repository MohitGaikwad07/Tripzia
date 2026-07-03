from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0004_booking"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="RouteHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("route_title", models.CharField(max_length=255)),
                ("destination", models.CharField(max_length=200)),
                ("total_estimated_cost", models.CharField(blank=True, max_length=100)),
                ("days", models.PositiveIntegerField(default=1)),
                ("budget", models.CharField(blank=True, max_length=50)),
                ("trip_snapshot", models.JSONField(blank=True, default=dict)),
                ("admin_notes", models.TextField(blank=True)),
                ("viewed_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="route_histories", to="auth.user")),
            ],
            options={
                "ordering": ["-viewed_at"],
            },
        ),
    ]
