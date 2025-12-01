from __future__ import annotations

import hashlib
import json

from django.db import migrations, models
import django.db.models.deletion


def _normalize_for_hash(value) -> str:
    if value is None:
        return "null"
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def forwards(apps, schema_editor):
    Payload = apps.get_model("dat", "DATPartPayload")
    Entry = apps.get_model("dat", "DATPartEntry")
    db_alias = schema_editor.connection.alias
    queryset = Entry.objects.using(db_alias).filter(value__isnull=False)
    for entry in queryset.iterator(chunk_size=500):
        raw_value = entry.value
        if raw_value in (None, "", [], {}, ()):
            entry.payload = None
            entry.value = None
            entry.save(update_fields=["payload", "value"])
            continue
        normalized = _normalize_for_hash(raw_value)
        payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        payload, _ = Payload.objects.using(db_alias).get_or_create(
            hash=payload_hash,
            defaults={"data": raw_value},
        )
        entry.payload = payload
        entry.value = None
        entry.save(update_fields=["payload", "value"])


def backwards(apps, schema_editor):
    Payload = apps.get_model("dat", "DATPartPayload")
    Entry = apps.get_model("dat", "DATPartEntry")
    db_alias = schema_editor.connection.alias
    queryset = Entry.objects.using(db_alias).filter(payload__isnull=False)
    for entry in queryset.iterator(chunk_size=500):
        payload = entry.payload
        entry.value = getattr(payload, "data", None)
        entry.payload = None
        entry.save(update_fields=["payload", "value"])
    # Optionally cleanup payloads with no references
    Payload.objects.using(db_alias).filter(entries__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dat", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DATPartPayload",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("data", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "dat_part_payload",
                "ordering": ["hash"],
            },
        ),
        migrations.AddField(
            model_name="datpartentry",
            name="payload",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="entries",
                to="dat.datpartpayload",
                verbose_name="Payload dédupliqué",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
