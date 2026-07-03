from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0006_booking_payment_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="booking",
            name="amount_paise",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="payment_method",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="payment_status",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="razorpay_order_id",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="razorpay_payment_id",
        ),
        migrations.RemoveField(
            model_name="booking",
            name="razorpay_signature",
        ),
    ]
