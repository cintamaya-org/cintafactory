from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dat", "0016_dat_subsection_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="dat",
            name="pdf_export_in_progress",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="dat",
            name="pdf_export_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dat",
            name="pdf_export_requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="dat",
            name="pdf_export_requested_by_display",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
