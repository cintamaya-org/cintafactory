from django.db import migrations, models

from users.profile_pictures import build_profile_picture_storage_name, get_profile_picture_storage


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0007_rename_user_oauth_account_provider_email_idx_user_oauth__provide_03e1e1_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_picture",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=get_profile_picture_storage(),
                upload_to=build_profile_picture_storage_name,
            ),
        ),
    ]
