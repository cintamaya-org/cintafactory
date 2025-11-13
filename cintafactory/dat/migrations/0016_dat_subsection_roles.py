from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0015_dat_structure_refactor"),
        ("users", "0009_alter_user_options_alter_user_date_joined_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="datsubsection",
            name="allowed_roles",
            field=models.ManyToManyField(
                blank=True,
                related_name="editable_dat_sub_sections",
                to="users.role",
                verbose_name="Rôles autorisés",
            ),
        ),
    ]
