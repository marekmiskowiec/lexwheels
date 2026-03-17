from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_managers_user_bio_user_display_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='avatar_key',
            field=models.CharField(
                choices=[
                    ('flame-red', 'Flame Red'),
                    ('track-orange', 'Track Orange'),
                    ('garage-blue', 'Garage Blue'),
                    ('mint-green', 'Mint Green'),
                    ('sunburst-yellow', 'Sunburst Yellow'),
                    ('midnight-black', 'Midnight Black'),
                    ('chrome-silver', 'Chrome Silver'),
                    ('purple-rush', 'Purple Rush'),
                    ('teal-speed', 'Teal Speed'),
                    ('sand-racer', 'Sand Racer'),
                ],
                default='flame-red',
                max_length=32,
            ),
        ),
    ]
