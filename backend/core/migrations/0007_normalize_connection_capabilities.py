from django.db import migrations


def normalize_capabilities(apps, schema_editor):
    Connection = apps.get_model("core", "IntegrationConnection")
    for connection in Connection.objects.select_related("provider").all().iterator():
        if not connection.enabled_capabilities or any("." not in item for item in connection.enabled_capabilities):
            connection.enabled_capabilities = connection.provider.capabilities
            connection.save(update_fields=["enabled_capabilities", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("core", "0006_semantic_read_views")]
    operations = [migrations.RunPython(normalize_capabilities, migrations.RunPython.noop)]
