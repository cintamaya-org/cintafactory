from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OAuthAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=50)),
                ("provider_user_id", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("access_token", models.TextField(blank=True)),
                ("refresh_token", models.TextField(blank=True)),
                ("token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("token_type", models.CharField(blank=True, max_length=40)),
                ("scope", models.TextField(blank=True)),
                ("raw_profile", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="oauth_accounts", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "db_table": "user_oauth_account",
                "ordering": ["provider", "id"],
                "unique_together": {("provider", "provider_user_id")},
                "indexes": [
                    models.Index(fields=["provider", "email"], name="user_oauth_account_provider_email_idx"),
                    models.Index(fields=["user", "provider"], name="user_oauth_account_user_provider_idx"),
                ],
            },
        ),
    ]
