from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0007_remove_history_status_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DATReserveHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section_slug", models.SlugField(blank=True, max_length=100)),
                ("section_title", models.CharField(blank=True, max_length=200)),
                ("reserve_message", models.TextField(blank=True)),
                ("reserved_by_display", models.CharField(blank=True, max_length=255)),
                ("reserved_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dat",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reserve_history_entries", to="dat.dat"),
                ),
                (
                    "reserved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dat_reserve_history_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "dat_reserve_history",
                "ordering": ["-reserved_at", "-id"],
            },
        ),
    ]
