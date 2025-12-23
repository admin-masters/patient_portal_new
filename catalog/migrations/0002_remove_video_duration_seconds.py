from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # If your project already has later migrations, update this dependency accordingly.
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="video",
            name="duration_seconds",
        ),
    ]
