# Generated manually (Django unavailable in the editing sandbox)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_player_ref_code_player_ref_earned_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='telegram_task_claimed',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
