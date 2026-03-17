from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_user_login'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='first_name',
        ),
        migrations.RemoveField(
            model_name='user',
            name='last_name',
        ),
    ]
