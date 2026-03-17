from django.db import migrations


def sync_display_names(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.all():
        user.display_name = user.login
        user.save(update_fields=['display_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_remove_user_first_name_remove_user_last_name'),
    ]

    operations = [
        migrations.RunPython(sync_display_names, migrations.RunPython.noop),
    ]
