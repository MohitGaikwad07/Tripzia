from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0005_routehistory"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="amount_paise",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="booking",
            name="payment_method",
            field=models.CharField(default="razorpay", max_length=50),
        ),
        migrations.AddField(
            model_name="booking",
            name="payment_status",
            field=models.CharField(default="pending", max_length=30),
        ),
        migrations.AddField(
            model_name="booking",
            name="razorpay_order_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="booking",
            name="razorpay_payment_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="booking",
            name="razorpay_signature",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
