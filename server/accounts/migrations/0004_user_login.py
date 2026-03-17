from django.db import migrations, models


def populate_logins(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    used = set()

    for user in User.objects.order_by('id'):
        base = (user.email.partition('@')[0] or 'user').strip().lower()
        candidate = base or 'user'
        suffix = 1

        while candidate in used:
            suffix += 1
            candidate = f'{base}{suffix}'

        user.login = candidate
        user.save(update_fields=['login'])
        used.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_avatar_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='login',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.RunPython(populate_logins, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='login',
            field=models.CharField(max_length=80, unique=True),
        ),
    ]
