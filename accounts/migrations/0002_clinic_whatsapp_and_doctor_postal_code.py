from __future__ import annotations

from django.db import migrations, models
import django.core.validators


def backfill_doctor_postal_code(apps, schema_editor):
    DoctorProfile = apps.get_model("accounts", "DoctorProfile")
    # Copy existing clinic.postal_code into doctorprofile.postal_code where missing
    for dp in DoctorProfile.objects.select_related("clinic").all():
        try:
            if (not dp.postal_code) and dp.clinic and dp.clinic.postal_code:
                dp.postal_code = dp.clinic.postal_code
                dp.save(update_fields=["postal_code"])
        except Exception:
            continue


class Migration(migrations.Migration):

    dependencies = [
        # If your project already has later migrations, update this dependency accordingly.
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinic",
            name="clinic_whatsapp_number",
            field=models.CharField(
                blank=True,
                max_length=10,
                validators=[
                    django.core.validators.RegexValidator(
                        "^\d{10}$",
                        "Enter a 10-digit WhatsApp number (without country code).",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="doctorprofile",
            name="postal_code",
            field=models.CharField(
                blank=True,
                max_length=6,
                validators=[
                    django.core.validators.RegexValidator(
                        "^\d{6}$",
                        "Enter a valid 6-digit PIN code.",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="doctorprofile",
            name="whatsapp_number",
            field=models.CharField(
                max_length=10,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^\d{10}$",
                        "Enter a 10-digit WhatsApp number (without country code).",
                    )
                ],
            ),
        ),
        migrations.RunPython(backfill_doctor_postal_code, migrations.RunPython.noop),
    ]
