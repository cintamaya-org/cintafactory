from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0002_datpartpayload"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="datpartentry",
            name="value",
        ),
    ]
