from django.db import migrations, models


def rename_content_types(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="diagrams", model="diagram").update(model="drawiodiagram")
    ContentType.objects.filter(app_label="diagrams", model="likec4file").update(model="likec4diagram")


def restore_content_types(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="diagrams", model="drawiodiagram").update(model="diagram")
    ContentType.objects.filter(app_label="diagrams", model="likec4diagram").update(model="likec4file")


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0007_diagram_png_paths"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel("Diagram", "DrawIODiagram"),
                migrations.RenameModel("LikeC4File", "LikeC4Diagram"),
                migrations.AlterModelTable(name="drawiodiagram", table="diagrams_diagram"),
                migrations.AlterModelTable(name="likec4diagram", table="diagrams_likec4file"),
            ],
        ),
        migrations.RunPython(rename_content_types, restore_content_types),
        migrations.AddField(
            model_name="likec4diagram",
            name="title",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
